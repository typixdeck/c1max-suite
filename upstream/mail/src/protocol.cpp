#include "protocol.hpp"
#include <mbedtls/ctr_drbg.h>
#include <mbedtls/entropy.h>
#include <mbedtls/error.h>
#include <mbedtls/net_sockets.h>
#include <mbedtls/ssl.h>
#include <mbedtls/x509_crt.h>
#include <algorithm>
#include <array>
#include <cerrno>
#include <charconv>
#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <memory>
#include <mutex>
#include <netdb.h>
#include <poll.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <thread>
#include <unistd.h>

namespace mail {
bool Operation::check(std::string &error)const{
    if(cancelled_.load(std::memory_order_relaxed)){error="Cancelled";return false;}
    if(std::chrono::steady_clock::now()>=deadline){error="Mail operation timed out";return false;}
    return true;
}
namespace {
constexpr size_t max_line=4096,max_wire=3*1024*1024,max_message=256*1024;
constexpr size_t max_list_entries=10000,max_reply_lines=100,max_message_lines=16384;
struct Address {sockaddr_storage value{};socklen_t size=0;int family=0;};
struct Resolution {std::atomic<bool> done{false};int error=0;std::vector<Address> addresses;};
// libc DNS is not safely interruptible. Keep at most ONE outstanding resolver
// thread, owning only its copied host and bounded result. A cancelled caller
// leaves immediately; retries cannot accumulate resolver threads. Process exit
// never joins a stalled resolver. No callbacks or UI objects cross this boundary.
struct ResolverGate {std::atomic<bool> busy{false};};
std::shared_ptr<ResolverGate> resolver_gate(){static auto gate=std::make_shared<ResolverGate>();return gate;}
#ifdef MAIL_NETWORK_TEST
std::atomic<int> resolver_delay_ms{0};
#endif
bool resolve(const std::string&host,const std::string&port,std::vector<Address>&out,const Operation&op,std::string&error){
    if(!op.check(error))return false;
    auto result=std::make_shared<Resolution>();
    auto gate=resolver_gate();bool expected=false;
    if(!gate->busy.compare_exchange_strong(expected,true)){error="A previous DNS lookup is still finishing; retry shortly";return false;}
    try{
        std::thread([gate,result,host,port]{
            try{
#ifdef MAIL_NETWORK_TEST
                std::this_thread::sleep_for(std::chrono::milliseconds(resolver_delay_ms.load()));
#endif
                addrinfo hints{};hints.ai_socktype=SOCK_STREAM;hints.ai_family=AF_UNSPEC;hints.ai_flags=AI_NUMERICSERV;
                addrinfo*raw=nullptr;result->error=getaddrinfo(host.c_str(),port.c_str(),&hints,&raw);
                std::unique_ptr<addrinfo,decltype(&freeaddrinfo)> addresses(raw,freeaddrinfo);
                if(!result->error)for(auto*p=raw;p&&result->addresses.size()<8;p=p->ai_next){
                    if((p->ai_family!=AF_INET&&p->ai_family!=AF_INET6)||p->ai_addrlen>sizeof(sockaddr_storage))continue;
                    Address a;a.family=p->ai_family;a.size=p->ai_addrlen;std::memcpy(&a.value,p->ai_addr,a.size);result->addresses.push_back(a);
                }
            }catch(...){result->error=EAI_MEMORY;}
            result->done.store(true,std::memory_order_release);gate->busy.store(false);
        }).detach();
    }catch(...){gate->busy=false;error="Could not start DNS lookup";return false;}
    while(!result->done.load(std::memory_order_acquire)){
        if(!op.check(error))return false;
        std::this_thread::sleep_for(std::chrono::milliseconds(20));
    }
    if(!op.check(error))return false;
    if(result->error||result->addresses.empty()){error="Mail server name could not be resolved";return false;}
    out=std::move(result->addresses);return true;
}
int socket_send(void*context,const unsigned char*data,size_t length){
    int fd=static_cast<mbedtls_net_context*>(context)->fd;
#ifdef MSG_NOSIGNAL
    int count=::send(fd,data,length,MSG_NOSIGNAL);
#else
    int count=::send(fd,data,length,0);
#endif
    if(count>=0)return count;
    if(errno==EAGAIN||errno==EWOULDBLOCK||errno==EINTR)return MBEDTLS_ERR_SSL_WANT_WRITE;
    return MBEDTLS_ERR_NET_SEND_FAILED;
}
class Stream {
    const Operation&operation_;
    mbedtls_net_context net_{};mbedtls_ssl_context ssl_{};mbedtls_ssl_config conf_{};mbedtls_x509_crt ca_{};mbedtls_ctr_drbg_context rng_{};mbedtls_entropy_context entropy_{};
    bool connected_=false,tls_=false;std::string pending_;size_t received_=0,written_=0;
    std::string tls_error(int rc){char buf[256];mbedtls_strerror(rc,buf,sizeof buf);return std::string(buf)+" ("+std::to_string(rc)+")";}
    bool wait(short events,std::string&error){
        while(operation_.check(error)){
            pollfd fd{net_.fd,events,0};int rc=poll(&fd,1,50);
            if(rc>0){if(fd.revents&POLLNVAL){error="Mail socket closed";return false;}return true;}
            if(rc<0&&errno!=EINTR){error="Mail socket wait failed";return false;}
        }
        return false;
    }
    bool retry(int rc,std::string&error){return wait(rc==MBEDTLS_ERR_SSL_WANT_WRITE?POLLOUT:POLLIN,error);}
public:
    explicit Stream(const Operation&operation):operation_(operation){mbedtls_net_init(&net_);mbedtls_ssl_init(&ssl_);mbedtls_ssl_config_init(&conf_);mbedtls_x509_crt_init(&ca_);mbedtls_ctr_drbg_init(&rng_);mbedtls_entropy_init(&entropy_);}
    ~Stream(){close();mbedtls_ssl_free(&ssl_);mbedtls_ssl_config_free(&conf_);mbedtls_x509_crt_free(&ca_);mbedtls_ctr_drbg_free(&rng_);mbedtls_entropy_free(&entropy_);}
    bool check(std::string&error){return operation_.check(error);}
    bool connect(const std::string&host,const std::string&port,bool implicit,std::string&error){
        unsigned port_number=0;auto parsed=std::from_chars(port.data(),port.data()+port.size(),port_number);
        if(host.empty()||host.size()>253||host.find_first_of("\r\n \t/\\")!=std::string::npos||host.find('\0')!=std::string::npos||port.empty()||parsed.ec!=std::errc()||parsed.ptr!=port.data()+port.size()||port_number<1||port_number>65535){error="Invalid mail server address";return false;}
        std::vector<Address> addresses;if(!resolve(host,port,addresses,operation_,error))return false;
        for(const auto&a:addresses){
            if(!check(error))return false;
            net_.fd=socket(a.family,SOCK_STREAM,0);if(net_.fd<0)continue;
            fcntl(net_.fd,F_SETFD,FD_CLOEXEC);
#ifdef SO_NOSIGPIPE
            int no_signal=1;setsockopt(net_.fd,SOL_SOCKET,SO_NOSIGPIPE,&no_signal,sizeof no_signal);
#endif
            int flags=fcntl(net_.fd,F_GETFL,0);
            if(flags<0||fcntl(net_.fd,F_SETFL,flags|O_NONBLOCK)<0){mbedtls_net_free(&net_);continue;}
            int rc=::connect(net_.fd,reinterpret_cast<const sockaddr*>(&a.value),a.size);
            if(rc<0&&errno==EINPROGRESS){
                if(!wait(POLLOUT,error)){mbedtls_net_free(&net_);return false;}
                int code=0;socklen_t length=sizeof(code);rc=getsockopt(net_.fd,SOL_SOCKET,SO_ERROR,&code,&length);if(rc==0&&code)rc=-1;
            }
            if(rc==0){connected_=true;return !implicit||start_tls(host,error);}
            mbedtls_net_free(&net_);
        }
        error="Could not connect to mail server";return false;
    }
    bool start_tls(const std::string&host,std::string&error){
        if(!check(error))return false;
        if(!connected_||!pending_.empty()){error="Unexpected data at TLS upgrade";return false;}
        const char*pers="Typix-Mail";int rc=mbedtls_ctr_drbg_seed(&rng_,mbedtls_entropy_func,&entropy_,reinterpret_cast<const unsigned char*>(pers),std::strlen(pers));
        if(rc){error="TLS random source failed";return false;}
        struct stat cert_stat{};
        if(stat(operation_.options.ca_file.c_str(),&cert_stat)||!S_ISREG(cert_stat.st_mode)||cert_stat.st_size<=0||cert_stat.st_size>8*1024*1024){error="Could not load TLS root certificates";return false;}
        rc=mbedtls_x509_crt_parse_file(&ca_,operation_.options.ca_file.c_str());if(rc<0){error="Could not parse TLS root certificates";return false;}
        if(!check(error))return false;
        rc=mbedtls_ssl_config_defaults(&conf_,MBEDTLS_SSL_IS_CLIENT,MBEDTLS_SSL_TRANSPORT_STREAM,MBEDTLS_SSL_PRESET_DEFAULT);
        if(rc){error="TLS setup failed";return false;}
        mbedtls_ssl_conf_authmode(&conf_,MBEDTLS_SSL_VERIFY_REQUIRED);mbedtls_ssl_conf_ca_chain(&conf_,&ca_,nullptr);mbedtls_ssl_conf_rng(&conf_,mbedtls_ctr_drbg_random,&rng_);
        mbedtls_ssl_conf_min_version(&conf_,MBEDTLS_SSL_MAJOR_VERSION_3,MBEDTLS_SSL_MINOR_VERSION_3);
        if((rc=mbedtls_ssl_setup(&ssl_,&conf_))||(rc=mbedtls_ssl_set_hostname(&ssl_,host.c_str()))){error="TLS setup: "+tls_error(rc);return false;}
        mbedtls_ssl_set_bio(&ssl_,&net_,socket_send,mbedtls_net_recv,nullptr);
        for(;;){
            if(!check(error))return false;
            rc=mbedtls_ssl_handshake(&ssl_);
            if(rc!=MBEDTLS_ERR_SSL_WANT_READ&&rc!=MBEDTLS_ERR_SSL_WANT_WRITE)break;
            if(!retry(rc,error))return false;
        }
        if(rc||mbedtls_ssl_get_verify_result(&ssl_)){error="TLS certificate or handshake rejected: "+tls_error(rc);return false;}
        tls_=true;return true;
    }
    bool write_all(const std::string&data,std::string&error){
        if(data.size()>max_wire-written_){error="Mail transaction exceeds output limit";return false;}
        size_t at=0;
        while(at<data.size()){
            if(!check(error))return false;
            int count=tls_?mbedtls_ssl_write(&ssl_,reinterpret_cast<const unsigned char*>(data.data()+at),std::min<size_t>(data.size()-at,16384)):socket_send(&net_,reinterpret_cast<const unsigned char*>(data.data()+at),data.size()-at);
            if(count==MBEDTLS_ERR_SSL_WANT_READ||count==MBEDTLS_ERR_SSL_WANT_WRITE){if(!retry(count,error))return false;continue;}
            if(count<=0){error="Mail connection write failed";return false;}
            at+=count;written_+=count;
        }
        return true;
    }
    bool read_line(std::string&line,std::string&error){
        for(;;){
            if(!check(error))return false;
            auto end=pending_.find('\n');
            if((end!=std::string::npos&&end>max_line)||(end==std::string::npos&&pending_.size()>max_line)){error="Mail protocol line exceeds 4096 bytes";return false;}
            if(end!=std::string::npos){line=pending_.substr(0,end);pending_.erase(0,end+1);if(!line.empty()&&line.back()=='\r')line.pop_back();return true;}
            unsigned char buffer[4096];int count=tls_?mbedtls_ssl_read(&ssl_,buffer,sizeof buffer):mbedtls_net_recv(&net_,buffer,sizeof buffer);
            if(count==MBEDTLS_ERR_SSL_WANT_READ||count==MBEDTLS_ERR_SSL_WANT_WRITE){if(!retry(count,error))return false;continue;}
            if(count<=0){error="Mail connection closed before the response completed";return false;}
            if(size_t(count)>max_wire-received_){error="Mail transaction exceeds 3 MiB input limit";return false;}
            received_+=count;pending_.append(reinterpret_cast<char*>(buffer),count);
        }
    }
    void close(){
        // No blocking TLS close/QUIT handshake on cancellation or destruction.
        if(net_.fd>=0)mbedtls_net_free(&net_);
        connected_=tls_=false;pending_.clear();
    }
    bool tls()const{return tls_;}
};
std::string trim(std::string s){auto a=s.find_first_not_of(" \t\r\n");if(a==std::string::npos)return {};return s.substr(a,s.find_last_not_of(" \t\r\n")-a+1);}
std::string b64(const std::string&s){static const char*t="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";std::string o;unsigned v=0,b=0;for(unsigned char c:s){v=(v<<8)|c;b+=8;while(b>=6){b-=6;o+=t[(v>>b)&63];}}if(b)o+=t[(v<<(6-b))&63];while(o.size()%4)o+='=';return o;}
std::string b64decode(const std::string&s){static const char*t="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";std::string o;unsigned v=0,b=0;for(unsigned char c:s){if(c=='='||std::isspace(c))continue;auto p=std::strchr(t,c);if(!p)continue;v=(v<<6)|unsigned(p-t);b+=6;if(b>=8){b-=8;o+=char((v>>b)&255);}}return o;}
bool status(Stream&s,std::string&line,std::string&err){
    if(!s.read_line(line,err))return false;
    if(line!="+OK"&&line.rfind("+OK ",0)!=0){err="POP3 server rejected the request";return false;}
    return true;
}
bool smtp_reply(Stream&s,int expected,std::string&err){
    for(size_t lines=0;lines<max_reply_lines;lines++){
        std::string line;if(!s.read_line(line,err))return false;
        if(line.size()<3||!std::isdigit(static_cast<unsigned char>(line[0]))||!std::isdigit(static_cast<unsigned char>(line[1]))||!std::isdigit(static_cast<unsigned char>(line[2]))||(line.size()>3&&line[3]!=' '&&line[3]!='-')){err="Invalid SMTP response";return false;}
        int code=(line[0]-'0')*100+(line[1]-'0')*10+line[2]-'0';
        if(code!=expected){err="SMTP returned "+std::to_string(code)+" (expected "+std::to_string(expected)+")";return false;}
        if(line.size()==3||line[3]==' ')return true;
    }
    err="SMTP response exceeds 100 lines";return false;
}
bool pop_command(Stream&s,const std::string&cmd,std::string&err){return s.write_all(cmd+"\r\n",err);}

std::string decode_qp(std::string s){std::string o;for(size_t i=0;i<s.size();i++){if(s[i]=='='&&i+2<s.size()){if(s[i+1]=='\r'&&s[i+2]=='\n'){i+=2;continue;}auto hex=[](char c){if(c>='0'&&c<='9')return c-'0';if(c>='A'&&c<='F')return c-'A'+10;if(c>='a'&&c<='f')return c-'a'+10;return -1;};int a=hex(s[i+1]),b=hex(s[i+2]);if(a>=0&&b>=0){o+=char((a<<4)|b);i+=2;continue;}}o+=s[i];}return o;}
Message parse_message(unsigned number,const std::string&raw){Message m;m.number=number;auto split=raw.find("\r\n\r\n");size_t body_at=split==std::string::npos?std::string::npos:split+4;if(split==std::string::npos){split=raw.find("\n\n");if(split!=std::string::npos)body_at=split+2;}std::string hdr=raw.substr(0,split),body=body_at==std::string::npos?raw:raw.substr(body_at);size_t from=hdr.find("From:"),sub=hdr.find("Subject:");if(from!=std::string::npos){auto e=hdr.find('\n',from);m.from=trim(hdr.substr(from+5,e==std::string::npos?e:e-from-5));}if(sub!=std::string::npos){auto e=hdr.find('\n',sub);m.subject=trim(hdr.substr(sub+8,e==std::string::npos?e:e-sub-8));}auto transfer=hdr.find("Content-Transfer-Encoding:");if(transfer!=std::string::npos){auto e=hdr.find('\n',transfer);auto v=hdr.substr(transfer,e==std::string::npos?e:e-transfer);for(char&c:v)c=char(std::tolower((unsigned char)c));if(v.find("base64")!=std::string::npos)body=b64decode(body);else if(v.find("quoted-printable")!=std::string::npos)body=decode_qp(body);}auto mime=hdr.find("Content-Type:");if(mime!=std::string::npos){auto e=hdr.find('\n',mime);auto v=hdr.substr(mime,e==std::string::npos?e:e-mime);for(char&c:v)c=char(std::tolower((unsigned char)c));if(v.find("text/plain")==std::string::npos)body="(Message body is HTML or an unsupported MIME part. Headers are shown above.)\n\n"+body;}std::string normalized;normalized.reserve(body.size());for(size_t i=0;i<body.size();i++){if(body[i]=='\r'){if(i+1<body.size()&&body[i+1]=='\n')i++;normalized+='\n';}else normalized+=body[i];}m.body=normalized.substr(0,4096);return m;}
bool valid_address(const std::string&s){return !s.empty()&&s.find('@')!=std::string::npos&&s.find_first_of("\r\n <>")==std::string::npos;}
}
namespace {
bool credentials(const Config&c,std::string&error){
    for(const auto*value:{&c.username,&c.password}){
        if(value->empty()||value->size()>512||value->find_first_of("\r\n")!=std::string::npos||value->find('\0')!=std::string::npos){error="Set valid account credentials (maximum 512 bytes, no line breaks)";return false;}
    }
    return true;
}
bool implicit_tls(TlsMode mode,const std::string&port,const char*standard){return mode==TlsMode::Implicit||(mode==TlsMode::ByPort&&port==standard);}
bool list_entry(const std::string&line,unsigned&id,size_t&bytes){
    const char*begin=line.data();const char*end=begin+line.size();
    auto first=std::from_chars(begin,end,id);if(first.ec!=std::errc()||id==0||first.ptr==end||*first.ptr!=' ')return false;
    auto second=std::from_chars(first.ptr+1,end,bytes);return second.ec==std::errc()&&second.ptr==end;
}
}
#ifdef MAIL_NETWORK_TEST
void test_resolver_delay(int milliseconds){resolver_delay_ms=milliseconds;}
#endif
bool receive(const Config&c,std::vector<Message>&messages,std::string&error,const Operation&operation){
    error.clear();if(!operation.check(error)||!credentials(c,error))return false;
    Stream stream(operation);bool implicit=implicit_tls(c.pop_tls,c.pop_port,"995");
    if(!stream.connect(c.pop_host,c.pop_port,implicit,error))return false;
    std::string line;if(!status(stream,line,error))return false;
    if(!implicit&&(!pop_command(stream,"STLS",error)||!status(stream,line,error)||!stream.start_tls(c.pop_host,error)))return false;
    if(!stream.tls()){error="Refusing mailbox credentials without verified TLS";return false;}
    if(!pop_command(stream,"USER "+c.username,error)||!status(stream,line,error)||!pop_command(stream,"PASS "+c.password,error)||!status(stream,line,error)||!pop_command(stream,"LIST",error)||!status(stream,line,error))return false;
    std::vector<std::pair<unsigned,size_t>> ids;size_t entries=0;
    for(;;){
        if(!stream.read_line(line,error))return false;if(line==".")break;
        if(++entries>max_list_entries){error="Mailbox listing exceeds 10000 entries";return false;}
        unsigned id=0;size_t bytes=0;if(!list_entry(line,id,bytes)){error="Invalid POP3 listing entry";return false;}
        if(std::any_of(ids.begin(),ids.end(),[id](const auto&item){return item.first==id;})){error="Duplicate POP3 message number";return false;}
        ids.emplace_back(id,bytes);std::sort(ids.begin(),ids.end());if(ids.size()>8)ids.erase(ids.begin());
    }
    std::vector<Message> fresh;
    for(const auto&item:ids){
        if(item.second>max_message){error="A recent message exceeds 256 KiB; inbox was not changed";return false;}
        if(!pop_command(stream,"RETR "+std::to_string(item.first),error)||!status(stream,line,error))return false;
        std::string raw;size_t lines=0;
        for(;;){
            if(!stream.read_line(line,error))return false;if(line==".")break;
            if(++lines>max_message_lines){error="Message exceeds 16384 lines";return false;}
            if(!line.empty()&&line[0]=='.'){
                if(line.size()<2||line[1]!='.'){error="Invalid POP3 dot-stuffing";return false;}
                line.erase(0,1);
            }
            if(line.size()+2>max_message-raw.size()){error="Message exceeds 256 KiB; inbox was not changed";return false;}
            raw+=line;raw+="\r\n";
        }
        fresh.push_back(parse_message(item.first,raw));
    }
    if(!operation.check(error))return false;
    // Complete snapshot: cancellation/errors never replace the previous inbox.
    messages=std::move(fresh);return true;
}
bool send(const Config&c,const std::string&to,const std::string&subject,const std::string&body,std::string&error,const Operation&operation){
    error.clear();if(!operation.check(error)||!credentials(c,error))return false;
    std::string from=c.sender.empty()?c.username:c.sender;
    if(to.size()>254||from.size()>254||to.find('\0')!=std::string::npos||from.find('\0')!=std::string::npos||!valid_address(to)||!valid_address(from)){error="Set valid recipient and From addresses";return false;}
    if(subject.size()>998||body.size()>65536){error="Outgoing message exceeds subject (998 bytes) or body (64 KiB) limit";return false;}
    Stream stream(operation);bool implicit=implicit_tls(c.smtp_tls,c.smtp_port,"465");
    if(!stream.connect(c.smtp_host,c.smtp_port,implicit,error)||!smtp_reply(stream,220,error))return false;
    if(!implicit){
        if(!stream.write_all("EHLO typix.local\r\n",error)||!smtp_reply(stream,250,error)||!stream.write_all("STARTTLS\r\n",error)||!smtp_reply(stream,220,error)||!stream.start_tls(c.smtp_host,error))return false;
    }
    if(!stream.tls()){error="Refusing SMTP credentials without verified TLS";return false;}
    // EHLO is required after TLS for BOTH implicit SMTPS and STARTTLS.
    if(!stream.write_all("EHLO typix.local\r\n",error)||!smtp_reply(stream,250,error))return false;
    if(!stream.write_all("AUTH LOGIN\r\n",error)||!smtp_reply(stream,334,error)||!stream.write_all(b64(c.username)+"\r\n",error)||!smtp_reply(stream,334,error)||!stream.write_all(b64(c.password)+"\r\n",error)||!smtp_reply(stream,235,error))return false;
    if(!stream.write_all("MAIL FROM:<"+from+">\r\n",error)||!smtp_reply(stream,250,error)||!stream.write_all("RCPT TO:<"+to+">\r\n",error)||!smtp_reply(stream,250,error)||!stream.write_all("DATA\r\n",error)||!smtp_reply(stream,354,error))return false;
    std::string normalized;
    for(size_t i=0;i<body.size();i++){
        if(body[i]=='\r'){if(i+1<body.size()&&body[i+1]=='\n')i++;normalized+="\r\n";}
        else if(body[i]=='\n')normalized+="\r\n";else normalized+=body[i];
    }
    std::string stuffed;
    for(size_t at=0;at<normalized.size();at++){if((at==0||normalized[at-1]=='\n')&&normalized[at]=='.')stuffed+='.';stuffed+=normalized[at];}
    if(stuffed.size()<2||stuffed.compare(stuffed.size()-2,2,"\r\n"))stuffed+="\r\n";
    std::string message="From: <"+from+">\r\nTo: <"+to+">\r\nSubject: =?UTF-8?B?"+b64(subject)+"?=\r\nMIME-Version: 1.0\r\nContent-Type: text/plain; charset=UTF-8\r\nContent-Transfer-Encoding: 8bit\r\n\r\n"+stuffed+".\r\n";
    if(!stream.write_all(message,error)||!smtp_reply(stream,250,error)){
        error+="; delivery status unknown. Check the mailbox before retrying";return false;
    }
    // The final DATA 250 means accepted. A stalled/failed QUIT must never turn
    // this into a retryable failure or encourage an accidental duplicate send.
    error.clear();return true;
}
}

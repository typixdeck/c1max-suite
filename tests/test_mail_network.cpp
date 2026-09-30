// Synthetic transport runner. Never loads account files or accesses real mail.
#include "async.hpp"
#include <cassert>
#include <chrono>
#include <iomanip>
#include <iostream>
#include <thread>
using Clock=std::chrono::steady_clock;
int main(int argc,char**argv){
    assert(argc==8);
    const std::string kind=argv[1];
    mail::Config config;config.pop_host=config.smtp_host=argv[2];config.pop_port=config.smtp_port=argv[3];
    config.username=config.sender="fixture@example.test";config.password="synthetic-only";
    config.pop_tls=config.smtp_tls=std::string(argv[7])=="implicit"?mail::TlsMode::Implicit:mail::TlsMode::Upgrade;
    mail::Options options;options.ca_file=argv[4];options.timeout_ms=std::stoi(argv[5]);int cancel_ms=std::stoi(argv[6]);
    if(kind.rfind("dns-",0)==0)mail::test_resolver_delay(600);
    mail::AsyncJob job;auto start=Clock::now();
    if(kind=="smtp")assert(job.start_send(config,"receiver@example.test","Synthetic fixture","Hello\n.dot\n",options));
    else assert(job.start_receive(config,options));
    assert(!job.start_receive(config,options)); // Duplicate operation is refused.
    config.username="changed-after-start";config.password.clear(); // Worker must own copies.
    int ticks=0;bool cancelled=false;mail::AsyncJob::Result result;
    while(!job.take(result)){
        ++ticks;
        auto elapsed=std::chrono::duration_cast<std::chrono::milliseconds>(Clock::now()-start).count();
        if(cancel_ms>=0&&elapsed>=cancel_ms&&!cancelled){job.cancel();cancelled=true;}
        std::this_thread::sleep_for(std::chrono::milliseconds(5));
    }
    auto elapsed=std::chrono::duration_cast<std::chrono::milliseconds>(Clock::now()-start).count();
    bool resolver_bounded=true;
    if(kind.rfind("dns-",0)==0){
        mail::test_resolver_delay(0);config.username="fixture@example.test";config.password="synthetic-only";
        mail::Operation second(options);std::vector<mail::Message> old{{"old","old","old",99}};std::string error;
        assert(!mail::receive(config,old,error,second));
        resolver_bounded=error.find("previous DNS lookup")!=std::string::npos;
        assert(resolver_bounded&&old.size()==1&&old[0].number==99);
    }
    std::cout<<"{\"success\":"<<(result.success?"true":"false")<<",\"error\":"<<std::quoted(result.error)
             <<",\"elapsed_ms\":"<<elapsed<<",\"ticks\":"<<ticks<<",\"count\":"<<result.messages.size()
             <<",\"resolver_bounded\":"<<(resolver_bounded?"true":"false")<<",\"numbers\":[";
    for(size_t i=0;i<result.messages.size();i++){if(i)std::cout<<',';std::cout<<result.messages[i].number;}
    std::cout<<"]}"<<std::endl;
    return 0;
}

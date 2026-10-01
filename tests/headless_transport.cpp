// Rendering fixture only: keep every external transport unavailable. The UI
// below is compiled from the production application sources, not re-created.
#include "display.hpp"
#include "net.hpp"
#include "../upstream/mail/src/protocol.hpp"
#include <fstream>
#include <stdexcept>
namespace screen {
bool quit=false,playing=false,tap=false;
bool open(){return false;} void close(){} void portrait(bool){}
uint32_t tick(){return 0;} bool caps_lock(){return false;}
uint32_t take_key(){return 0;} bool video_begin(){return false;}
void video_frame(const uint32_t*,int,int,int,int){} void video_fit(bool){}
void video_controls(bool,bool){} void video_controls_area(int,int){}
void video_caption(const uint32_t*,int,int){} void video_refresh(bool){} void video_end(){}
}
namespace c1 {
void cancel_requests(){} void reset_requests(int){}
std::string root(){return "upstream";} std::string data(){return "/nonexistent/typix-layout-fixture";}
std::string read_file(const std::string &path,size_t maximum){
    std::ifstream file(path,std::ios::binary);if(!file)throw std::runtime_error("Fixture file unavailable");
    std::string out;char buffer[4096];while(file){file.read(buffer,sizeof buffer);out.append(buffer,file.gcount());if(out.size()>maximum)throw std::runtime_error("Fixture file too large");}return out;
}
void save_private(const std::string&,const std::string&){throw std::runtime_error("Rendering fixture cannot persist data");}
Response http(const std::string&,const std::string&,const std::vector<std::string>&,const std::string&,const std::atomic<bool>*,int){throw std::runtime_error("Rendering fixture is offline");}
}
namespace mail {
bool receive(const Config&,std::vector<Message>&,std::string &error,const Operation&){error="Rendering fixture is offline";return false;}
bool send(const Config&,const std::string&,const std::string&,const std::string&,std::string &error,const Operation&){error="Rendering fixture is offline";return false;}
}

// Exercise the production Player and Y4M decoder; display and audio are sinks.
#include "player.hpp"
#include <chrono>
#include <csignal>
#include <filesystem>
#include <iostream>
#include <unistd.h>
namespace screen {
bool playing=false,tap=false;
uint32_t tick(){return std::chrono::duration_cast<std::chrono::milliseconds>(
    std::chrono::steady_clock::now().time_since_epoch()).count();}
bool video_begin(){return true;}
void video_frame(const uint32_t*,int,int,int,int){}
void video_refresh(bool){}
void video_end(){}
}
int main(int argc,char**argv){
    if(argc!=3||!getenv("C1_APPS_DATA"))return 2;
    signal(SIGPIPE,SIG_IGN);setenv("C1_BILI_SILENT","1",1);
    std::filesystem::create_directories(c1::data()+"/bilibili");
    bili::Player player;player.start({argv[1],20,16});
    const auto begin=screen::tick();
    while(player.active()&&player.error.empty()&&player.frames()<20&&screen::tick()-begin<12000){
        player.poll();usleep(5000);
    }
    const bool ok=player.frames()>=20;
    const bool forbidden=player.error.find("403")!=std::string::npos;
    player.stop();
    // Never emit a playback URL or MPlayer's raw transport diagnostics.
    std::cout<<"decoded="<<ok<<" forbidden="<<forbidden<<'\n';
    return (std::string(argv[2])=="decode"?ok:std::string(argv[2])=="403"?forbidden:!ok)?0:1;
}

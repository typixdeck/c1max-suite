// Opt-in anonymous live transport acceptance. No GUI, account or history access.
#include "player.hpp"
#include <chrono>
#include <csignal>
#include <filesystem>
#include <iostream>
#include <stdexcept>
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
int main(){
    if(!getenv("C1_APPS_DATA"))return 2;
    signal(SIGPIPE,SIG_IGN);setenv("C1_BILI_SILENT","1",1);
    unsetenv("C1_BILI_QA_LOCAL");c1::reset_requests(10000);
    std::filesystem::create_directories(c1::data()+"/bilibili");
    std::string stage="api";bool forbidden=false,decoded=false;uint64_t frames=0;
    try{
        // Api is newly constructed and anonymous. It never reads session files.
        bili::Api api;auto listing=api.popular(1);Json selected;
        for(auto& item:listing.at("items"))if(item.value("duration",0)>=10){selected=item;break;}
        if(selected.is_null())throw std::runtime_error("No eligible public video");
        auto detail=api.detail(selected.at("bvid"));
        auto source=api.stream(detail.at("bvid"),detail.at("pages")[0].at("cid"));
        stage="playback";bili::Player player;player.start(source);
        auto begin=screen::tick();
        while(player.active()&&player.error.empty()&&player.frames()<20&&screen::tick()-begin<20000){
            player.poll();usleep(5000);
        }
        frames=player.frames();decoded=frames>=20;
        forbidden=player.error.find("403")!=std::string::npos;
        if(!decoded&&player.error.empty())stage="playback_timeout";
        player.stop();
    }catch(const std::exception& error){
        // Do not emit the server message, account data, chosen BV or signed URL.
        forbidden=std::string(error.what()).find("403")!=std::string::npos;
    }
    std::cout<<Json{{"decoded",decoded},{"frames",frames},{"forbidden",forbidden},
        {"stage",stage},{"anonymous",true},{"physicalAudio",false}}.dump()<<'\n';
    return decoded?0:1;
}

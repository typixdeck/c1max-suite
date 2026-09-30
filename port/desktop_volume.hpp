#pragma once
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <cerrno>
#include <spawn.h>
#include <sys/wait.h>
extern char **environ;
// Normal user desktop audio control. No ALSA card number or vendor mixer name.
inline int desktop_volume(){
 FILE*f=popen("wpctl get-volume @DEFAULT_AUDIO_SINK@ 2>/dev/null","r");if(!f)return -1;
 char line[128]{};auto ok=fgets(line,sizeof line,f);int rc=pclose(f);double v=0;
 return ok&&rc==0&&sscanf(line,"Volume: %lf",&v)==1?std::clamp(int(v*100),0,100):-1;
}
inline void desktop_volume_set(int value){
 std::string v=std::to_string(std::clamp(value,0,100))+"%";
 char *args[]={const_cast<char*>("wpctl"),const_cast<char*>("set-volume"),const_cast<char*>("@DEFAULT_AUDIO_SINK@"),v.data(),nullptr};pid_t p;
 if(posix_spawnp(&p,"wpctl",nullptr,nullptr,args,environ)==0){int status;while(waitpid(p,&status,0)<0&&errno==EINTR){}}
}

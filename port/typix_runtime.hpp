#pragma once
#include <cstdlib>
#include <cstdio>
#include <filesystem>
#include <string>
#include <unistd.h>
#include <sys/stat.h>
inline bool typix_runtime_init(){
 try{
  char executable[4096]{};ssize_t n=readlink("/proc/self/exe",executable,sizeof executable-1);if(n<=0)return false;
  std::string name=std::filesystem::path(std::string(executable,n)).filename().string();
  if(name.rfind("c1max-",0)==0)name="typix-"+name.substr(6);
  if(!getenv("C1_APPS_ROOT"))setenv("C1_APPS_ROOT",("/usr/share/"+name).c_str(),1);
  if(!getenv("C1_APPS_DATA")){
   const char*xdg=getenv("XDG_DATA_HOME"),*home=getenv("HOME");
   if(!xdg&&!home){fputs("A user home/data directory is required.\n",stderr);return false;}
   std::string data=xdg?xdg:std::string(home)+"/.local/share";data+="/typix-c1max";
   setenv("C1_APPS_DATA",data.c_str(),1);
  }
  umask(0077);std::filesystem::create_directories(getenv("C1_APPS_DATA"));
  std::string app=name.rfind("typix-",0)==0?name.substr(6):name;
  std::filesystem::create_directories(std::filesystem::path(getenv("C1_APPS_DATA"))/app);
  if(!getenv("TYPIX_APP_NAME"))setenv("TYPIX_APP_NAME",name.c_str(),1);
  setenv("TYPIX_APP_ID",name.c_str(),1);
  return true;
 }catch(const std::exception&e){fprintf(stderr,"Cannot prepare private application data: %s\n",e.what());return false;}
}

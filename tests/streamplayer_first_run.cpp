#include "typix_runtime.hpp"
#include "client.hpp"
#include "net.hpp"
#include <cassert>
#include <sys/stat.h>
int main(int argc,char**argv){
 assert(argc==2);assert(typix_runtime_init());
 auto path=c1::data()+"/streamplayer/config.json";assert(access(path.c_str(),F_OK)!=0);
 MediaClient client;client.load();client.login(argv[1],"fixture-user","fixture-password","Jellyfin");
 auto saved=Json::parse(c1::read_file(path));assert(saved.at("token")=="fixture-token");assert(saved.at("user_id")=="fixture-id");
 assert(!saved.contains("password"));assert(c1::read_file(path).find("fixture-password")==std::string::npos);
 struct stat st{};assert(stat(path.c_str(),&st)==0);assert((st.st_mode&0777)==0600);
 client.load();assert(client.ready());puts("First-run directory, login persistence, private mode, reload and password exclusion passed");
}

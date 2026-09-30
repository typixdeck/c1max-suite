#pragma once
#include <cstdlib>
inline const char* desktop_player(){const char*p=getenv("TYPIX_MPLAYER");return p&&p[0]=='/'?p:"/usr/bin/mplayer";}

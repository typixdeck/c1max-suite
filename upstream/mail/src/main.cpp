#include "typix_runtime.hpp"
#include "display.hpp"
#include "typix_layout.hpp"
#include "net.hpp"
#include "protocol.hpp"
#include "async.hpp"
#include "lv_tiny_ttf.h"
#include <lvgl.h>
#include <algorithm>
#include <csignal>
#include <cstdio>
#include <sys/stat.h>
#include <unistd.h>

namespace {
enum class Page { Inbox, Settings, Compose, Message };
Page page=Page::Inbox;
mail::Config account;
std::vector<mail::Message> messages;
std::string recipient,subject,body,status="Ready";
std::string edit_value;
int selected=0,settings_selected=0,compose_selected=0,message_scroll=0;
bool editing=false;
lv_font_t*font=nullptr;
constexpr uint32_t paper=0xf3eee2,ink=0x243431,teal=0x386c63,muted=0x738079,card=0xfffbf2,amber=0xb17941;
mail::AsyncJob job;
volatile sig_atomic_t stopped=0;
void stop_signal(int){stopped=1;}

std::string config_path(){return c1::data()+"/mail/account.json";}
void load_config(){try{auto j=Json::parse(c1::read_file(config_path(),16384));account.pop_host=j.value("pop_host","");account.pop_port=j.value("pop_port","995");account.smtp_host=j.value("smtp_host","");account.smtp_port=j.value("smtp_port","465");account.username=j.value("username","");account.password=j.value("password","");account.sender=j.value("sender","");}catch(...) {}}
void save_config(){try{Json j={{"pop_host",account.pop_host},{"pop_port",account.pop_port},{"smtp_host",account.smtp_host},{"smtp_port",account.smtp_port},{"username",account.username},{"password",account.password},{"sender",account.sender}};c1::save_private(config_path(),j.dump(2)+"\n");status="Account saved privately on this device";}catch(const std::exception&e){status=std::string("Save failed · ")+e.what();}}
std::string* setting_field(int n){switch(n){case 0:return &account.pop_host;case 1:return &account.pop_port;case 2:return &account.smtp_host;case 3:return &account.smtp_port;case 4:return &account.username;case 5:return &account.password;default:return &account.sender;}}
const char* setting_name(int n){static const char*names[]={"POP3 host","POP3 port","SMTP host","SMTP port","Username","Password","From address"};return names[std::clamp(n,0,6)];}
std::string mask(const std::string&s){std::string out;for(size_t i=0;i<s.size();i++)out+="●";return out;}
lv_obj_t* label(lv_obj_t*parent,const std::string&s,int x,int y,int w,int h,uint32_t color=ink,int size=18){auto*o=lv_label_create(parent);lv_label_set_text(o,s.c_str());lv_label_set_long_mode(o,LV_LABEL_LONG_MODE_WRAP);screen::place(o,x,y);screen::size(o,w,h);lv_obj_set_style_text_color(o,lv_color_hex(color),0);if(font)lv_obj_set_style_text_font(o,font,0);(void)size;return o;}
lv_obj_t*panel(lv_obj_t*parent,int x,int y,int w,int h,uint32_t color=card){auto*o=lv_obj_create(parent);lv_obj_remove_flag(o,LV_OBJ_FLAG_SCROLLABLE);screen::place(o,x,y);screen::size(o,w,h);lv_obj_set_style_bg_color(o,lv_color_hex(color),0);lv_obj_set_style_bg_opa(o,LV_OPA_COVER,0);lv_obj_set_style_border_color(o,lv_color_hex(0xd8d1c2),0);lv_obj_set_style_border_width(o,1,0);lv_obj_set_style_radius(o,11,0);lv_obj_set_style_shadow_width(o,0,0);return o;}
void key(uint32_t k);
void edit_touched_field(Page target,int index);
void header(const char*title,const char*subtitle){auto*r=lv_screen_active();lv_obj_clean(r);lv_obj_remove_flag(r,LV_OBJ_FLAG_SCROLLABLE);lv_obj_set_style_bg_color(r,lv_color_hex(paper),0);lv_obj_set_style_text_color(r,lv_color_hex(ink),0);if(font)lv_obj_set_style_text_font(r,font,0);label(r,title,18,8,220,30,ink,23);label(r,subtitle,236,13,225,24,muted,16);
    const char*names[]={"Receive","Compose","Account"};const uint32_t actions[]={'r','c','s'};
    for(int i=0;i<(page==Page::Inbox?3:1);++i){
        auto*button=lv_button_create(r);screen::place(button,page==Page::Inbox?468+i*106:678,5);screen::size(button,100,36);
        lv_obj_set_style_bg_color(button,lv_color_hex(teal),0);lv_obj_set_style_shadow_width(button,0,0);lv_obj_set_style_text_color(button,lv_color_hex(card),0);
        auto*text=lv_label_create(button);lv_label_set_text(text,page==Page::Inbox?names[i]:"Back");lv_obj_center(text);
        uint32_t action=page==Page::Inbox?actions[i]:screen::KEY_EXIT;
        lv_obj_add_event_cb(button,[](lv_event_t*e){key(uint32_t(uintptr_t(lv_event_get_user_data(e))));},LV_EVENT_CLICKED,reinterpret_cast<void*>(uintptr_t(action)));
    }
}
void paint();
void cancel_transfer(){job.cancel();status="Cancelling transfer… Draft and inbox are retained";paint();}
void footer(){
    label(lv_screen_active(),status,18,286,job.busy()?600:762,50,teal,16);
    if(job.busy()){
        auto*button=lv_button_create(lv_screen_active());screen::place(button,636,287);screen::size(button,146,43);
        auto*text=lv_label_create(button);lv_label_set_text(text,"Cancel / Esc");lv_obj_center(text);
        lv_obj_add_event_cb(button,[](lv_event_t*){cancel_transfer();},LV_EVENT_CLICKED,nullptr);
    }
}
void paint(){
    auto*r=lv_screen_active();
    if(page==Page::Inbox){header("Mail",account.username.empty()?"Account not configured":account.username.c_str());panel(r,14,47,772,232);label(r,"INBOX  /  LAST 8",28,55,735,22,muted,15);
        if(messages.empty())label(r,account.username.empty()?"No messages loaded.\n\nChoose Account to configure mail,\nthen Receive to load recent messages.":"No messages loaded.\n\nChoose Receive to load recent messages.",34,104,730,145,muted,19);
        else for(int i=0;i<(int)messages.size()&&i<8;i++){int y=82+i*23;std::string line=(i==selected?"›  ":"   ")+messages[i].from+"   ·   "+messages[i].subject;auto*row=label(r,line,29,y,735,24,i==selected?teal:ink,16);lv_obj_add_flag(row,LV_OBJ_FLAG_CLICKABLE);lv_obj_add_event_cb(row,[](lv_event_t*e){selected=int(intptr_t(lv_event_get_user_data(e)));key(LV_KEY_ENTER);},LV_EVENT_CLICKED,reinterpret_cast<void*>(intptr_t(i)));}
        footer();return;
    }
    if(page==Page::Settings){header("ACCOUNT","SERVER SETTINGS · Esc back");panel(r,14,48,772,232);for(int i=0;i<7;i++){int y=57+i*30;bool chosen=i==settings_selected;std::string val=*setting_field(i);if(i==5)val=mask(val);if(editing&&chosen)val=(i==5?mask(edit_value):edit_value)+"_";if(val.empty())val="(not set)";label(r,setting_name(i),32,y,172,25,chosen?teal:muted,16);auto*value=label(r,val,214,y,550,25,chosen?ink:0x59645f,16);lv_obj_add_flag(value,LV_OBJ_FLAG_CLICKABLE);lv_obj_add_event_cb(value,[](lv_event_t*e){edit_touched_field(Page::Settings,int(intptr_t(lv_event_get_user_data(e))));},LV_EVENT_CLICKED,reinterpret_cast<void*>(intptr_t(i)));if(chosen){auto*bar=lv_obj_create(r);lv_obj_remove_style_all(bar);screen::place(bar,19,y+4);screen::size(bar,4,17);lv_obj_set_style_bg_color(bar,lv_color_hex(amber),0);lv_obj_set_style_bg_opa(bar,LV_OPA_COVER,0);}}
        footer();return;
    }
    if(page==Page::Compose){header("NEW MESSAGE","SMTP · Select Send, then Enter to confirm");panel(r,14,48,772,232);std::string vals[]={recipient,subject,body,"SEND MESSAGE"};const char*names[]={"To","Subject","Message","Action"};for(int i=0;i<4;i++){int y=60+i*57;bool chosen=i==compose_selected;std::string val=vals[i];if(editing&&chosen)val=edit_value+"_";if(i==3)val=chosen?"[ SEND ]":"Send";if(val.empty())val="(empty)";label(r,names[i],32,y,120,26,chosen?teal:muted,17);auto*value=label(r,val,155,y,610,i==2?48:28,chosen?ink:0x59645f,17);lv_obj_add_flag(value,LV_OBJ_FLAG_CLICKABLE);lv_obj_add_event_cb(value,[](lv_event_t*e){edit_touched_field(Page::Compose,int(intptr_t(lv_event_get_user_data(e))));},LV_EVENT_CLICKED,reinterpret_cast<void*>(intptr_t(i)));if(chosen){auto*bar=lv_obj_create(r);lv_obj_remove_style_all(bar);screen::place(bar,19,y+4);screen::size(bar,4,18);lv_obj_set_style_bg_color(bar,lv_color_hex(amber),0);lv_obj_set_style_bg_opa(bar,LV_OPA_COVER,0);}}
        footer();return;
    }
    header("MESSAGE","Esc inbox · ↑↓ scroll");if(selected<0||selected>=int(messages.size())){page=Page::Inbox;paint();return;}auto&m=messages[selected];panel(r,14,48,772,232);label(r,"FROM  "+m.from,30,57,733,23,teal,16);label(r,m.subject,30,82,733,28,ink,19);std::string text=m.body;constexpr size_t chunk=620;size_t at=std::min<size_t>(std::max(0,message_scroll),text.size());label(r,text.substr(at,chunk),30,115,735,153,ink,16);status="↑↓ scroll message · Back to inbox";footer();
}
void finish_edit(){if(page==Page::Settings){*setting_field(settings_selected)=edit_value;save_config();}else if(page==Page::Compose){if(compose_selected==0)recipient=edit_value;else if(compose_selected==1)subject=edit_value;else if(compose_selected==2)body=edit_value;}editing=false;paint();}
void edit_touched_field(Page target,int index){
    if(job.busy()||page!=target)return;
    int current=target==Page::Settings?settings_selected:compose_selected;
    if(editing&&current==index)return;
    if(editing)finish_edit(); // Commit the previous field before moving focus.
    if(target==Page::Settings)settings_selected=index;else compose_selected=index;
    key(LV_KEY_ENTER);
}
std::string*compose_field(int n){if(n==0)return &recipient;if(n==1)return &subject;return &body;}
void send_message(){
    try{if(!job.start_send(account,recipient,subject,body))return;status="Sending securely… Esc or Cancel stops waiting";}
    catch(const std::exception&){status="Could not start transfer; draft retained";}
    paint();
}
void receive_mail(){
    try{if(!job.start_receive(account))return;status="Receiving securely… Esc or Cancel stops waiting";}
    catch(const std::exception&){status="Could not start transfer; inbox retained";}
    paint();
}
void poll_transfer(){
    mail::AsyncJob::Result result;if(!job.take(result))return;
    if(result.kind==mail::AsyncJob::Kind::Send){
        if(result.success){status="Message accepted by SMTP server";recipient.clear();subject.clear();body.clear();compose_selected=0;page=Page::Inbox;}
        else status="Send failed · "+result.error;
    }else if(result.success){messages=std::move(result.messages);selected=0;message_scroll=0;status="Fetched "+std::to_string(messages.size())+" recent messages";}
    else status="Receive failed · "+result.error;
    paint();
}
void key(uint32_t k){
    if(k==LV_KEY_ESC)k=screen::KEY_EXIT;
    if(k==screen::KEY_HOME){job.cancel();screen::quit=true;return;}
    if(job.busy()){if(k==screen::KEY_EXIT)cancel_transfer();return;}
    if(k==screen::KEY_MODE||k==screen::KEY_SYMBOL)return;
    if(editing){if(k==screen::KEY_EXIT){editing=false;paint();return;}if(k==LV_KEY_ENTER){finish_edit();return;}if(k==LV_KEY_BACKSPACE){if(!edit_value.empty()){size_t n=edit_value.size()-1;while(n>0&&(static_cast<unsigned char>(edit_value[n])&0xc0)==0x80)--n;edit_value.erase(n);}paint();return;}if(k>=32&&k<127){if(edit_value.size()<((page==Page::Compose&&compose_selected==2)?512:128))edit_value.push_back(char(k));paint();}return;}
    if(k==screen::KEY_EXIT){if(page==Page::Inbox){status="Ready";}else if(page==Page::Settings||page==Page::Compose){page=Page::Inbox;status="Ready";}else{page=Page::Inbox;message_scroll=0;status="Ready";}paint();return;}
    if(page==Page::Inbox){if(k=='r'||k=='R'){receive_mail();return;}if(k=='c'||k=='C'){page=Page::Compose;compose_selected=0;status="↑↓ choose · Enter edit / send · R clears draft";paint();return;}if(k=='s'||k=='S'){page=Page::Settings;status="↑↓ choose · Enter edit · S save account";paint();return;}if(k==LV_KEY_UP){if(!messages.empty())selected=(selected+(int)messages.size()-1)%messages.size();paint();return;}if(k==LV_KEY_DOWN){if(!messages.empty())selected=(selected+1)%messages.size();paint();return;}if(k==LV_KEY_ENTER&&!messages.empty()){page=Page::Message;message_scroll=0;paint();return;}}
    else if(page==Page::Settings){if(k==LV_KEY_UP)settings_selected=(settings_selected+6)%7;else if(k==LV_KEY_DOWN)settings_selected=(settings_selected+1)%7;else if(k==LV_KEY_ENTER){editing=true;edit_value=*setting_field(settings_selected);status="Type value · Enter saves · Esc cancels edit";}else if(k=='s'||k=='S')save_config();paint();return;}
    else if(page==Page::Compose){
        if(k==LV_KEY_UP)compose_selected=(compose_selected+3)%4;
        else if(k==LV_KEY_DOWN)compose_selected=(compose_selected+1)%4;
        else if(k==LV_KEY_ENTER){
            if(compose_selected==3){send_message();return;}
            editing=true;edit_value=*compose_field(compose_selected);status="Type message · Enter finishes · Esc cancels edit";
        }else if(k=='r'||k=='R'){recipient.clear();subject.clear();body.clear();status="Draft cleared";}
        paint();return;
    }
    else if(page==Page::Message){if(k==LV_KEY_UP)message_scroll=std::max(0,message_scroll-400);else if(k==LV_KEY_DOWN)message_scroll=std::min<int>(messages[selected].body.size(),message_scroll+400);paint();}
}
}
int main(){
    if(!typix_runtime_init())return 1;signal(SIGINT,stop_signal);signal(SIGTERM,stop_signal);mkdir((c1::data()+"/mail").c_str(),0700);load_config();if(!screen::open())return 1;font=lv_tiny_ttf_create_file(("A:"+c1::root()+"/shared/NotoSansSC-Regular.ttf").c_str(),18);paint();while(!stopped&&!screen::quit){lv_timer_handler();for(uint32_t k;(k=screen::take_key());)key(k);poll_transfer();usleep(10000);}job.cancel();lv_obj_clean(lv_screen_active());lv_obj_set_style_text_font(lv_screen_active(),LV_FONT_DEFAULT,0);if(font)lv_tiny_ttf_destroy(font);screen::close();return 0;}

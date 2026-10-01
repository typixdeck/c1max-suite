// Exercise production GTK Escape routing and each app's real state handlers.
#include <gtk/gtk.h>
#include <cassert>
#include <chrono>
#include <thread>
#define main original_application_main
#if defined(TEST_PROCESSING)
#include "../upstream/processing/src/main.cpp"
#elif defined(TEST_AIRTUNE)
#include "../upstream/airtune/src/main.cpp"
#else
#include "../upstream/streamplayer/src/main.cpp"
#endif
#undef main
static GtkWidget* find_widget(GtkWidget*w,const char*label){
 if(GTK_IS_BUTTON(w)&&std::string(gtk_widget_get_name(w))==label)return w;
 if(GTK_IS_CONTAINER(w)){GList*c=gtk_container_get_children(GTK_CONTAINER(w));GtkWidget*found=nullptr;for(auto*i=c;i&&!found;i=i->next)found=find_widget(GTK_WIDGET(i->data),label);g_list_free(c);return found;}return nullptr;
}
static uint32_t escape(bool touch){
 auto*list=gtk_window_list_toplevels();assert(list);GtkWidget*w=GTK_WIDGET(list->data);
 if(touch){auto*b=find_widget(w,"typix-back");assert(b);gtk_button_clicked(GTK_BUTTON(b));}
 else {GdkEventKey e{};e.type=GDK_KEY_PRESS;e.keyval=GDK_KEY_Escape;gboolean handled=FALSE;g_signal_emit_by_name(w,"key-press-event",&e,&handled);assert(handled);}
 g_list_free(list);auto k=screen::take_key();assert(k==screen::KEY_EXIT);assert(screen::take_key()==0);return k;
}
#if !defined(TEST_PROCESSING)
static void deliver(uint32_t k){
#ifdef TEST_AIRTUNE
 key(k);
#else
 physical_key(k);
#endif
}
static void drain(){auto until=std::chrono::steady_clock::now()+std::chrono::seconds(3);while(busy&&std::chrono::steady_clock::now()<until){lv_timer_handler();finish_request();std::this_thread::sleep_for(std::chrono::milliseconds(5));}assert(!busy);}
#endif
int main(int argc,char**argv){
 assert(screen::open());
#ifdef TEST_PROCESSING
 api=c1::read_file(c1::root()+"/processing/api.js",32768);chinese=false;library();
 for(bool touch:{false,true}){select(0);assert(page==Page::Run);key(escape(touch));assert(page==Page::Library);select(0);edit();assert(page==Page::Edit);key(escape(touch));assert(page==Page::Library);assert(c1::read_file(c1::data()+"/processing/my-sketch.js")==source);}
 puts("PASS: physical/context-header Escape returns from Processing run and saves editor");
#else
#ifdef TEST_AIRTUNE
 paint();
#else
 show_setup();
#endif
 assert(argc==2);int callbacks=0;
 for(bool touch:{false,true}){
  // A late successful worker must not overwrite UI after cancellation.
  work("Late result fixture",[]{std::this_thread::sleep_for(std::chrono::milliseconds(100));return Json::object();},[&](const Json&){++callbacks;});
  deliver(escape(touch));assert(request_cancelled&&busy);
  work("Must wait",[]{return Json::object();},[&](const Json&){callbacks+=100;});
  drain();assert(callbacks==0&&!request_cancelled);
  // The next request can complete after the previous worker has drained.
  work("Retry",[]{return Json::object();},[&](const Json&){++callbacks;});drain();assert(callbacks==1);callbacks=0;
  // Actual wget request to a loopback peer that accepts but sends no response.
  std::string url=argv[1];work("Stalled loopback",[url]{c1::http("GET",url);return Json::object();},[&](const Json&){++callbacks;});
  std::this_thread::sleep_for(std::chrono::milliseconds(150));auto before=std::chrono::steady_clock::now();deliver(escape(touch));drain();assert(callbacks==0);assert(std::chrono::steady_clock::now()-before<std::chrono::milliseconds(1500));
 }
 puts("PASS: physical/context-header Escape cancels HTTP, rejects late completion, waits before retry, then recovers");
#endif
 lv_obj_clean(lv_screen_active());screen::close();return 0;
}

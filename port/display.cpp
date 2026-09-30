// TypixDeck compositor port for the C1Max LVGL applications.
// No framebuffer, evdev, power, USB configuration, or root access.
#include "display.hpp"
#include "keyboard.hpp"
#include <gtk/gtk.h>
#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <vector>
#include <ctime>
#include <fstream>
namespace screen {
bool quit=false,playing=false,tap=false;
static GtkWidget *window=nullptr,*area=nullptr;
static std::vector<uint32_t> pixels(800*800),video,caption;
static uint32_t buffer[800*32];
static std::deque<uint32_t> keys;
static int width=800,height=340,vw=0,vh=0,capw=0,caph=0,mouse_x=0,mouse_y=0;
static int controls_top=0,controls_bottom=340;
static bool down=false,video_active=false,show_controls=true,full_controls=false,fill=true;
static double offset_x=0,offset_y=0,scale=1;
static uint32_t started=0;
static bool caps=false,soft_shift=false;
uint32_t tick(){timespec t{};clock_gettime(CLOCK_MONOTONIC,&t);return uint32_t(t.tv_sec*1000+t.tv_nsec/1000000);}
static void push(uint32_t k){if(k){if(keys.size()>128)keys.pop_front();keys.push_back(k);}}
static void save_capture(){
 const char *path=getenv("TYPIX_CAPTURE");if(!path)return;
 auto*s=cairo_image_surface_create_for_data(reinterpret_cast<unsigned char*>(pixels.data()),CAIRO_FORMAT_ARGB32,width,height,width*4);
 cairo_surface_write_to_png(s,path);cairo_surface_destroy(s);
}
static void pump(){
 while(gtk_events_pending())gtk_main_iteration_do(FALSE);
 const char *limit=getenv("TYPIX_SMOKE_MS");if(limit&&tick()-started>strtoul(limit,nullptr,10)){save_capture();quit=true;}
}
static gboolean draw(GtkWidget*w,cairo_t*c,gpointer){
 int aw=gtk_widget_get_allocated_width(w),ah=gtk_widget_get_allocated_height(w);
 scale=std::min(double(aw)/width,double(ah)/height);offset_x=(aw-width*scale)/2;offset_y=(ah-height*scale)/2;
 cairo_set_source_rgb(c,0.035,0.05,0.08);cairo_paint(c);cairo_translate(c,offset_x,offset_y);cairo_scale(c,scale,scale);
 if(video_active&&!video.empty()){
  auto*s=cairo_image_surface_create_for_data((unsigned char*)video.data(),CAIRO_FORMAT_RGB24,vw,vh,vw*4);
  cairo_save(c);double factor=fill?std::max(double(width)/vw,double(height)/vh):std::min(double(width)/vw,double(height)/vh);
  cairo_translate(c,(width-vw*factor)/2,(height-vh*factor)/2);cairo_scale(c,factor,factor);cairo_set_source_surface(c,s,0,0);cairo_paint(c);cairo_restore(c);cairo_surface_destroy(s);
 }
 if(!video_active||show_controls){
  auto*s=cairo_image_surface_create_for_data((unsigned char*)pixels.data(),CAIRO_FORMAT_ARGB32,width,height,width*4);
  cairo_save(c);if(video_active&&!full_controls){cairo_rectangle(c,0,0,width,controls_top);cairo_rectangle(c,0,controls_bottom,width,height-controls_bottom);cairo_clip(c);}
  cairo_set_source_surface(c,s,0,0);cairo_paint(c);cairo_restore(c);cairo_surface_destroy(s);
 }
 if(video_active&&!caption.empty()){
  auto*s=cairo_image_surface_create_for_data((unsigned char*)caption.data(),CAIRO_FORMAT_ARGB32,capw,caph,capw*4);
  cairo_set_source_surface(c,s,(width-capw)/2,std::max(0,(show_controls?controls_bottom:height)-caph-8));cairo_paint(c);cairo_surface_destroy(s);
 }
 return TRUE;
}
static gboolean key_event(GtkWidget*,GdkEventKey*e,gpointer){
 if(e->type!=GDK_KEY_PRESS)return FALSE;
 caps=(e->state&GDK_LOCK_MASK)!=0;
 if(e->keyval==GDK_KEY_F10){quit=true;return TRUE;}
 if(e->keyval==GDK_KEY_F11){GdkWindow*w=gtk_widget_get_window(window);if(gdk_window_get_state(w)&GDK_WINDOW_STATE_FULLSCREEN)gtk_window_unfullscreen(GTK_WINDOW(window));else gtk_window_fullscreen(GTK_WINDOW(window));return TRUE;}
 if(e->state&GDK_MOD1_MASK)return FALSE; // compositor owns Alt+Tab
 uint32_t k=0;
 switch(e->keyval){case GDK_KEY_Escape:k=KEY_EXIT;break;case GDK_KEY_Return:case GDK_KEY_KP_Enter:k=LV_KEY_ENTER;break;case GDK_KEY_BackSpace:k=LV_KEY_BACKSPACE;break;
 case GDK_KEY_Tab:k=LV_KEY_NEXT;break;case GDK_KEY_Left:k=LV_KEY_LEFT;break;case GDK_KEY_Right:k=LV_KEY_RIGHT;break;case GDK_KEY_Up:k=LV_KEY_UP;break;case GDK_KEY_Down:k=LV_KEY_DOWN;break;
 case GDK_KEY_Home:k=LV_KEY_HOME;break;case GDK_KEY_End:k=LV_KEY_END;break;case GDK_KEY_Delete:k=LV_KEY_DEL;break;case GDK_KEY_F2:k=KEY_SYMBOL;break;case GDK_KEY_F3:k=KEY_HOME;break;
 default:k=gdk_keyval_to_unicode(e->keyval);if((e->state&GDK_CONTROL_MASK)&&k>=32&&k<127){push(KEY_SYMBOL);k=uint32_t(g_ascii_tolower(k));}break;}
 push(k);return k!=0;
}
static gboolean pointer(GtkWidget*,GdkEvent*e,gpointer){
 double x=0,y=0;
 if(e->type==GDK_MOTION_NOTIFY){x=e->motion.x;y=e->motion.y;}
 else if(e->type==GDK_BUTTON_PRESS||e->type==GDK_BUTTON_RELEASE){x=e->button.x;y=e->button.y;down=e->type==GDK_BUTTON_PRESS;if(down)tap=true;}
 else if(e->type==GDK_TOUCH_BEGIN||e->type==GDK_TOUCH_UPDATE||e->type==GDK_TOUCH_END){x=e->touch.x;y=e->touch.y;down=e->type!=GDK_TOUCH_END;if(e->type==GDK_TOUCH_BEGIN)tap=true;}
 else return FALSE;
 mouse_x=std::clamp(int((x-offset_x)/scale),0,width-1);mouse_y=std::clamp(int((y-offset_y)/scale),0,height-1);return TRUE;
}
static void flush(lv_display_t*d,const lv_area_t*a,uint8_t*p){
 auto*src=reinterpret_cast<uint32_t*>(p);
 for(int y=a->y1;y<=a->y2;y++)for(int x=a->x1;x<=a->x2;x++){uint32_t pixel=*src++;if(x>=0&&x<width&&y>=0&&y<height)pixels[size_t(y)*width+x]=pixel|0xff000000;}
 lv_display_flush_ready(d);if(area)gtk_widget_queue_draw(area);
}
static void input(lv_indev_t*,lv_indev_data_t*d){pump();d->point.x=mouse_x;d->point.y=mouse_y;d->state=down?LV_INDEV_STATE_PRESSED:LV_INDEV_STATE_RELEASED;}
static void click_key(GtkButton*b,gpointer p){uint32_t k=GPOINTER_TO_UINT(p);if(soft_shift&&k>='a'&&k<='z')k-=32;push(k);gtk_widget_grab_focus(area);}
static void text_activate(GtkEntry*entry,gpointer){const char*t=gtk_entry_get_text(entry);while(*t){push(g_utf8_get_char(t));t=g_utf8_next_char(t);}gtk_entry_set_text(entry,"");gtk_widget_grab_focus(area);}
bool open(){
 g_set_prgname(getenv("TYPIX_APP_ID")?getenv("TYPIX_APP_ID"):"typix-application");
 if(!gtk_init_check(nullptr,nullptr)){g_printerr("A Wayland or X11 desktop session is required.\n");return false;}
 quit=false;started=tick();window=gtk_window_new(GTK_WINDOW_TOPLEVEL);gtk_window_set_title(GTK_WINDOW(window),getenv("TYPIX_APP_NAME")?getenv("TYPIX_APP_NAME"):"TypixDeck");gtk_window_set_default_size(GTK_WINDOW(window),800,600);
 g_signal_connect(window,"delete-event",G_CALLBACK(+[](GtkWidget*,GdkEvent*,gpointer)->gboolean{quit=true;return TRUE;}),nullptr);
 g_signal_connect(window,"key-press-event",G_CALLBACK(+[](GtkWidget*w,GdkEventKey*e,gpointer p)->gboolean{if(e->keyval==GDK_KEY_Escape||e->keyval==GDK_KEY_F10||e->keyval==GDK_KEY_F11)return key_event(w,e,p);return FALSE;}),nullptr);
 GtkWidget*box=gtk_box_new(GTK_ORIENTATION_VERTICAL,0);gtk_container_add(GTK_CONTAINER(window),box);area=gtk_drawing_area_new();gtk_widget_set_can_focus(area,TRUE);gtk_widget_add_events(area,GDK_BUTTON_PRESS_MASK|GDK_BUTTON_RELEASE_MASK|GDK_POINTER_MOTION_MASK|GDK_TOUCH_MASK);
 gtk_box_pack_start(GTK_BOX(box),area,TRUE,TRUE,0);g_signal_connect(area,"draw",G_CALLBACK(draw),nullptr);g_signal_connect(area,"event",G_CALLBACK(pointer),nullptr);g_signal_connect(area,"key-press-event",G_CALLBACK(key_event),nullptr);
 GtkWidget*bar=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,2);gtk_box_pack_start(GTK_BOX(box),bar,FALSE,FALSE,4);
 const char*labels[]={"Esc","Tab","←","→","↑","↓","Enter","F2","Exit"};uint32_t values[]={KEY_EXIT,LV_KEY_NEXT,LV_KEY_LEFT,LV_KEY_RIGHT,LV_KEY_UP,LV_KEY_DOWN,LV_KEY_ENTER,KEY_SYMBOL,KEY_HOME};
 for(unsigned i=0;i<9;i++){GtkWidget*b=gtk_button_new_with_label(labels[i]);gtk_box_pack_start(GTK_BOX(bar),b,FALSE,FALSE,0);if(i==8)g_signal_connect(b,"clicked",G_CALLBACK(+[](GtkButton*,gpointer){quit=true;}),nullptr);else g_signal_connect(b,"clicked",G_CALLBACK(click_key),GUINT_TO_POINTER(values[i]));}
 GtkWidget*keyboard_panel=gtk_box_new(GTK_ORIENTATION_VERTICAL,2);
 gtk_style_context_add_class(gtk_widget_get_style_context(keyboard_panel),"typix-keyboard");
 GtkCssProvider*css=gtk_css_provider_new();gtk_css_provider_load_from_data(css,".typix-keyboard button { min-width: 18px; padding: 5px; }",-1,nullptr);gtk_style_context_add_provider_for_screen(gdk_screen_get_default(),GTK_STYLE_PROVIDER(css),GTK_STYLE_PROVIDER_PRIORITY_APPLICATION);g_object_unref(css);
 gtk_box_pack_end(GTK_BOX(box),keyboard_panel,FALSE,FALSE,0);
 for(const char*row:{"1234567890+-=*/()", "qwertyuiop[]", "asdfghjkl;:'", "zxcvbnm,.?!@", "_#$%&<>\\|^~`{}"}){
  GtkWidget*r=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,2);gtk_box_pack_start(GTK_BOX(keyboard_panel),r,FALSE,FALSE,0);
  for(const char*p=row;*p;p++){char label[]={*p,0};GtkWidget*b=gtk_button_new_with_label(label);gtk_widget_set_hexpand(b,TRUE);gtk_box_pack_start(GTK_BOX(r),b,TRUE,TRUE,0);g_signal_connect(b,"clicked",G_CALLBACK(click_key),GUINT_TO_POINTER(uint32_t(*p)));}
 }
 GtkWidget*r=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,2);gtk_box_pack_start(GTK_BOX(keyboard_panel),r,FALSE,FALSE,0);
 GtkWidget*shift=gtk_toggle_button_new_with_label("Shift");gtk_box_pack_start(GTK_BOX(r),shift,TRUE,TRUE,0);g_signal_connect(shift,"toggled",G_CALLBACK(+[](GtkToggleButton*b,gpointer){soft_shift=gtk_toggle_button_get_active(b);}),nullptr);
 for(auto item:{std::pair<const char*,uint32_t>{"Space",32},{"Backspace",LV_KEY_BACKSPACE},{"Enter",LV_KEY_ENTER}}){GtkWidget*b=gtk_button_new_with_label(item.first);gtk_box_pack_start(GTK_BOX(r),b,TRUE,TRUE,0);g_signal_connect(b,"clicked",G_CALLBACK(click_key),GUINT_TO_POINTER(item.second));}
 GtkWidget*toggle=gtk_button_new_with_label("Keys");gtk_box_pack_start(GTK_BOX(bar),toggle,FALSE,FALSE,0);
 g_signal_connect(toggle,"clicked",G_CALLBACK(+[](GtkButton*,gpointer p){GtkWidget*w=GTK_WIDGET(p);gtk_widget_set_visible(w,!gtk_widget_get_visible(w));}),keyboard_panel);
 GtkWidget*entry=gtk_entry_new();gtk_entry_set_width_chars(GTK_ENTRY(entry),6);gtk_entry_set_max_width_chars(GTK_ENTRY(entry),12);gtk_entry_set_placeholder_text(GTK_ENTRY(entry),"Text → Enter");gtk_box_pack_start(GTK_BOX(bar),entry,TRUE,TRUE,0);g_signal_connect(entry,"activate",G_CALLBACK(text_activate),nullptr);
 lv_init();lv_tick_set_cb(tick);auto*d=lv_display_create(width,height);lv_display_set_color_format(d,LV_COLOR_FORMAT_ARGB8888);lv_display_set_buffers(d,buffer,nullptr,sizeof buffer,LV_DISPLAY_RENDER_MODE_PARTIAL);lv_display_set_flush_cb(d,flush);
 auto*i=lv_indev_create();lv_indev_set_type(i,LV_INDEV_TYPE_POINTER);lv_indev_set_read_cb(i,input);
 gtk_widget_show_all(keyboard_panel);gtk_widget_hide(keyboard_panel);gtk_widget_set_no_show_all(keyboard_panel,TRUE);gtk_widget_show_all(window);gtk_window_resize(GTK_WINDOW(window),800,600);gtk_widget_grab_focus(area);if(!getenv("TYPIX_WINDOWED")||std::strcmp(getenv("TYPIX_WINDOWED"),"1"))gtk_window_fullscreen(GTK_WINDOW(window));return true;
}
void close(){video_end();if(window)gtk_widget_destroy(window);window=area=nullptr;keys.clear();}
uint32_t take_key(){pump();if(keys.empty())return 0;auto k=keys.front();keys.pop_front();return k;}
bool caps_lock(){return caps;}
void portrait(bool enabled){width=enabled?340:800;height=enabled?800:340;std::fill(pixels.begin(),pixels.end(),0xff000000);lv_display_set_resolution(lv_display_get_default(),width,height);lv_obj_invalidate(lv_screen_active());}
bool video_begin(){video_active=true;return true;}
void video_frame(const uint32_t*p,int w,int h,int,int){if(w<1||h<1||w>1920||h>1080)return;video.assign(p,p+size_t(w)*h);vw=w;vh=h;if(area)gtk_widget_queue_draw(area);}
void video_fit(bool enabled){fill=enabled;}
void video_controls(bool visible,bool full){show_controls=visible;full_controls=full;}
void video_controls_area(int top,int bottom){controls_top=top;controls_bottom=bottom;}
void video_caption(const uint32_t*p,int w,int h){caption.clear();if(p&&w>0&&h>0){capw=w;caph=h;caption.assign(p,p+size_t(w)*h);for(auto&v:caption){unsigned a=v>>24;v=(a<<24)|(((v>>16&255)*a/255)<<16)|(((v>>8&255)*a/255)<<8)|((v&255)*a/255);}}}
void video_refresh(bool){pump();if(area)gtk_widget_queue_draw(area);}
void video_end(){video_active=false;video.clear();caption.clear();}
}
namespace keyboard {void open(){}void close(){}void poll(){}uint32_t take(){return screen::take_key();}bool caps_lock(){return screen::caps_lock();}}

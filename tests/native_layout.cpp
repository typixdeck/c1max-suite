// Real LVGL rendering and interaction, without a window server or device I/O.
#include <cassert>
#include <cmath>
#include <cstring>
#include <filesystem>
#include <string>
#include <vector>
#include <cairo.h>
#include "typix_layout.hpp"
#define main original_application_main
#if defined(TEST_CALCULATOR)
#include "../upstream/calculator/src/main.cpp"
#elif defined(TEST_CALENDAR)
#include "../upstream/calendar/src/main.cpp"
#elif defined(TEST_MAIL)
#include "../upstream/mail/src/main.cpp"
#endif
#undef main
namespace {
std::vector<uint32_t> framebuffer;
uint32_t draw_buffer[800*32];
lv_display_t *display=nullptr;
uint32_t fake_time=0;
int frame_width=800,frame_height=600;
void flush_frame(lv_display_t *d,const lv_area_t *rect,uint8_t *bytes){
    auto *source=reinterpret_cast<uint32_t*>(bytes);
    for(int y=rect->y1;y<=rect->y2;++y){
        if(y>=0&&y<frame_height)std::memcpy(framebuffer.data()+y*frame_width+rect->x1,source,(rect->x2-rect->x1+1)*4);
        source+=rect->x2-rect->x1+1;
    }
    lv_display_flush_ready(d);
}
void viewport(int w,int h){
    frame_width=w;frame_height=h;framebuffer.assign(w*h,0);
    lv_display_set_resolution(display,w,h);screen::layout_viewport(w,h);
}
void save_frame(const std::string &path){
    lv_obj_update_layout(lv_screen_active());fake_time+=100;lv_obj_invalidate(lv_screen_active());lv_refr_now(display);
    auto *surface=cairo_image_surface_create_for_data(reinterpret_cast<unsigned char*>(framebuffer.data()),CAIRO_FORMAT_ARGB32,frame_width,frame_height,frame_width*4);
    assert(cairo_surface_write_to_png(surface,path.c_str())==CAIRO_STATUS_SUCCESS);cairo_surface_destroy(surface);
}
lv_obj_t *button_named(lv_obj_t *root,const char *name){
    if(lv_obj_check_type(root,&lv_button_class)){
        for(uint32_t i=0;i<lv_obj_get_child_count(root);++i){auto *child=lv_obj_get_child(root,i);if(lv_obj_check_type(child,&lv_label_class)&&std::string(lv_label_get_text(child))==name)return root;}
    }
    for(uint32_t i=0;i<lv_obj_get_child_count(root);++i)if(auto *found=button_named(lv_obj_get_child(root,i),name))return found;
    return nullptr;
}
void click(const char *name){auto *button=button_named(lv_screen_active(),name);assert(button);lv_obj_send_event(button,LV_EVENT_CLICKED,nullptr);}
void assert_root_bounds(){
    lv_obj_update_layout(lv_screen_active());
    for(uint32_t i=0;i<lv_obj_get_child_count(lv_screen_active());++i){
        auto *child=lv_obj_get_child(lv_screen_active(),i);lv_area_t rect;lv_obj_get_coords(child,&rect);
        assert(rect.x1>=0&&rect.y1>=0&&rect.x2<frame_width&&rect.y2<frame_height);
    }
}
void layout_regression(){
    auto *root=lv_screen_active();lv_obj_remove_flag(root,LV_OBJ_FLAG_SCROLLABLE);
    auto *panel=lv_obj_create(root);lv_obj_remove_style_all(panel);screen::place(panel,20,40);screen::size(panel,300,120);
    auto *text=lv_label_create(panel);lv_label_set_text(text,"Center");lv_obj_center(text);
    auto font_height=lv_obj_get_style_text_font(text,LV_PART_MAIN)->line_height;
    viewport(1024,768);lv_obj_update_layout(root);
    assert(lv_obj_get_x(panel)==26&&lv_obj_get_y(panel)==90);
    assert(lv_obj_get_width(panel)==384&&lv_obj_get_height(panel)==271);
    assert(lv_obj_get_style_align(text,LV_PART_MAIN)==LV_ALIGN_CENTER);
    assert(lv_obj_get_style_text_font(text,LV_PART_MAIN)->line_height==font_height);
    auto *relative=lv_obj_create(root);screen::set_width(relative,LV_PCT(50));screen::set_height(relative,LV_SIZE_CONTENT);
    viewport(1280,800);lv_obj_update_layout(root);assert(lv_obj_get_width(relative)==640);
    auto *image=lv_obj_create(root);lv_obj_remove_style_all(image);screen::place(image,20,40);screen::size(image,300,120);
    lv_obj_update_layout(root);lv_area_t rect;lv_obj_get_coords(image,&rect);lv_point_t source;
    lv_point_t center{(rect.x1+rect.x2+1)/2,(rect.y1+rect.y2+1)/2};
    assert(screen::image_point(image,center,100,100,&source));assert(std::abs(source.x-50)<=1&&std::abs(source.y-50)<=1);
    lv_point_t margin{rect.x1,center.y};assert(!screen::image_point(image,margin,100,100,&source));
    lv_obj_clean(root); // Repeated clean/reflow must not retain deleted widgets.
    viewport(800,600);viewport(1024,768);viewport(800,600);
    screen::layout_design(true);auto *tall=lv_obj_create(root);screen::place(tall,10,20);screen::size(tall,300,700);assert_root_bounds();
    lv_obj_clean(root);screen::layout_design(false);
}
}
int main(int argc,char **argv){
    assert(argc==2);std::filesystem::create_directories(argv[1]);
    lv_init();lv_tick_set_cb([]{return fake_time;});
    display=lv_display_create(800,600);lv_display_set_color_format(display,LV_COLOR_FORMAT_ARGB8888);
    lv_display_set_buffers(display,draw_buffer,nullptr,sizeof draw_buffer,LV_DISPLAY_RENDER_MODE_PARTIAL);lv_display_set_flush_cb(display,flush_frame);
    viewport(800,600);layout_regression();
    const char *font_path="A:upstream/shared/fonts/NotoSansSC-Regular.ttf";
#if defined(TEST_CALCULATOR)
    body_font=lv_tiny_ttf_create_file(font_path,22);result_font=lv_tiny_ttf_create_file(font_path,38);assert(body_font&&result_font);chinese=true;
    create_ui();click("2");click("+");click("3");click("=");assert(model.display()=="5");
    click("AC");physical_key('1');physical_key('2');physical_key('*');physical_key('7');physical_key(LV_KEY_ENTER);refresh();assert(model.display()=="84");
    const char *app="calculator";
#elif defined(TEST_CALENDAR)
    font=lv_tiny_ttf_create_file(font_path,18);assert(font);selected={2026,10,1};month={2026,10,1};refresh_events();render();
    assert(grid.size()==42);click("N 新增");assert(page==Page::Edit);back();assert(page==Page::Month);const char *app="calendar";
#elif defined(TEST_MAIL)
    font=lv_tiny_ttf_create_file(font_path,18);assert(font);messages={{"Example sender","Planning a quiet weekend","This is a synthetic offline rendering fixture.",1}};paint();
    click("Compose");assert(page==Page::Compose);edit_touched_field(Page::Compose,0);key('a');edit_touched_field(Page::Compose,1);assert(recipient=="a"&&editing&&compose_selected==1);key(screen::KEY_EXIT);key(screen::KEY_EXIT);assert(page==Page::Inbox);
    const char *app="mail";
#endif
    for(auto resolution:{std::pair{800,600},std::pair{1024,768},std::pair{1280,800}}){
        viewport(resolution.first,resolution.second);assert_root_bounds();
        save_frame(std::string(argv[1])+"/"+app+"-responsive-"+std::to_string(resolution.first)+"x"+std::to_string(resolution.second)+".png");
    }
    lv_obj_clean(lv_screen_active());lv_obj_set_style_text_font(lv_screen_active(),LV_FONT_DEFAULT,0);
#if defined(TEST_CALCULATOR)
    lv_tiny_ttf_destroy(body_font);lv_tiny_ttf_destroy(result_font);
#else
    lv_tiny_ttf_destroy(font);
#endif
    screen::layout_clear();lv_display_delete(display);lv_deinit();
    std::printf("PASS %s: source UI, reflow, bounds, touch/keyboard, aspect-preserving hit tests\n",app);
}

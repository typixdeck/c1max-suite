#include "typix_layout.hpp"
#include <algorithm>
#include <cmath>
#include <unordered_map>
#include <vector>

namespace screen {
namespace {
struct Geometry {
    int x=0, y=0, w=0, h=0;
    bool position=false, width=false, height=false;
};
std::unordered_map<lv_obj_t *, Geometry> objects;
int viewport_w=800, viewport_h=600, design_w=800, design_h=340;
std::function<void()> resized;
int dimension(int value, int native, int design) {
    if (!LV_COORD_IS_PX(value)) return value; // Percent and CONTENT stay native.
    return int(std::lround(double(value)*native/design));
}
Geometry &geometry(lv_obj_t *object) {
    auto [entry, added]=objects.try_emplace(object);
    if (added) lv_obj_add_event_cb(object, [](lv_event_t *event) {
        objects.erase(static_cast<lv_obj_t *>(lv_event_get_target(event)));
    }, LV_EVENT_DELETE, nullptr);
    return entry->second;
}
void apply(lv_obj_t *object, const Geometry &g) {
    auto align=lv_obj_get_style_align(object, LV_PART_MAIN);
    if (g.position && (align==LV_ALIGN_TOP_LEFT || align==LV_ALIGN_DEFAULT))
        lv_obj_set_pos(object, layout_x(g.x), layout_y(g.y));
    if (g.width) lv_obj_set_width(object, dimension(g.w, viewport_w, design_w));
    if (g.height) lv_obj_set_height(object, dimension(g.h, viewport_h, design_h));
}
void reflow() {
    // A size event may delete another object; never retain map iterators across it.
    std::vector<lv_obj_t *> pending;
    pending.reserve(objects.size());
    for (const auto &item:objects) pending.push_back(item.first);
    for (auto *object:pending) {
        auto found=objects.find(object);
        if (found!=objects.end()) {
            auto value=found->second;
            apply(object, value);
        }
    }
    if (resized) resized();
}
}
int layout_width() { return viewport_w; }
int layout_height() { return viewport_h; }
int layout_x(int value) { return dimension(value, viewport_w, design_w); }
int layout_y(int value) { return dimension(value, viewport_h, design_h); }
void place(lv_obj_t *object,int x,int y) {
    auto &g=geometry(object);g.x=x;g.y=y;g.position=true;
    lv_obj_set_pos(object,layout_x(x),layout_y(y));
}
void size(lv_obj_t *object,int width,int height) {
    auto &g=geometry(object);g.w=width;g.h=height;g.width=g.height=true;
    lv_obj_set_size(object,dimension(width,viewport_w,design_w),dimension(height,viewport_h,design_h));
}
void set_width(lv_obj_t *object,int width) {
    auto &g=geometry(object);g.w=width;g.width=true;
    lv_obj_set_width(object,dimension(width,viewport_w,design_w));
}
void set_height(lv_obj_t *object,int height) {
    auto &g=geometry(object);g.h=height;g.height=true;
    lv_obj_set_height(object,dimension(height,viewport_h,design_h));
}
void layout_viewport(int width,int height) {
    width=std::clamp(width,320,1920);height=std::clamp(height,240,1440);
    if (width==viewport_w && height==viewport_h) return;
    viewport_w=width;viewport_h=height;reflow();
}
void layout_design(bool portrait) {
    int w=portrait?340:800,h=portrait?800:340;
    if (w==design_w && h==design_h) return;
    design_w=w;design_h=h;reflow();
}
void layout_on_resize(std::function<void()> callback) { resized=std::move(callback); }
void layout_clear() { objects.clear();resized={};design_w=800;design_h=340; }
bool image_point(lv_obj_t *image,const lv_point_t &point,int width,int height,lv_point_t *out) {
    if (!image || !out || width<=0 || height<=0) return false;
    lv_obj_update_layout(image);
    lv_area_t rect;lv_obj_get_coords(image,&rect);
    double ratio=std::min(double(lv_area_get_width(&rect))/width,double(lv_area_get_height(&rect))/height);
    if (ratio<=0) return false;
    double left=rect.x1+(lv_area_get_width(&rect)-width*ratio)/2;
    double top=rect.y1+(lv_area_get_height(&rect)-height*ratio)/2;
    if(point.x<left || point.y<top || point.x>=left+width*ratio || point.y>=top+height*ratio) return false;
    out->x=std::clamp(int((point.x-left)/ratio),0,width-1);
    out->y=std::clamp(int((point.y-top)/ratio),0,height-1);
    return true;
}
}

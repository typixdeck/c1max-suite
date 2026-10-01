#pragma once
#include "lvgl.h"
#include <functional>

// Layout the application's own widgets, not a stretched screenshot of a device.
// Fonts retain their proportions. Images use CONTAIN and retain their aspect ratio.
namespace screen {
void place(lv_obj_t *object, int x, int y);
void size(lv_obj_t *object, int width, int height);
void set_width(lv_obj_t *object, int width);
void set_height(lv_obj_t *object, int height);
void layout_viewport(int width, int height);
void layout_design(bool portrait);
int layout_width();
int layout_height();
int layout_x(int value);
int layout_y(int value);
void layout_on_resize(std::function<void()> callback);
void layout_clear();
// Hit-test an aspect-preserving image. Returns source-pixel coordinates.
bool image_point(lv_obj_t *image, const lv_point_t &point, int width, int height, lv_point_t *out);
}

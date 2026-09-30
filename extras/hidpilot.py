#!/usr/bin/python3
"""Manual HID keyboard/touchpad for already configured Linux gadget nodes."""
import argparse
from collections import deque
import glob
import os
import re
import select
import stat
import sys
import time

SPECIAL = {"Return": 40, "Escape": 41, "BackSpace": 42, "Tab": 43, "space": 44,
           "Insert": 73, "Home": 74, "Page_Up": 75, "Delete": 76, "End": 77,
           "Page_Down": 78, "Right": 79, "Left": 80, "Down": 81, "Up": 82}
SPECIAL.update({f"F{i}": 57 + i for i in range(1, 13)})
MODIFIERS = {"Control_L": 1, "Shift_L": 2, "Alt_L": 4, "Super_L": 8,
             "Control_R": 16, "Shift_R": 32, "Alt_R": 64, "Super_R": 128}


def ascii_key(char):
    if "a" <= char <= "z":
        return ord(char) - 97 + 4, 0
    if "A" <= char <= "Z":
        return ord(char) - 65 + 4, 2
    if char in "1234567890":
        return "1234567890".index(char) + 30, 0
    normal, shifted = "-=[]\\;\'`,./", '_+{}|:"~<>?'
    usages = (45, 46, 47, 48, 49, 51, 52, 53, 54, 55, 56)
    if char in normal:
        return usages[normal.index(char)], 0
    if char in shifted:
        return usages[shifted.index(char)], 2
    if char in "!@#$%^&*()":
        return "!@#$%^&*()".index(char) + 30, 2
    return {" ": (44, 0), "\n": (40, 0), "\t": (43, 0)}.get(char)


def keyboard_report(usages=(), modifiers=0, combined=False):
    usages = sorted(set(usages))
    if len(usages) > 6:
        usages = [1] * 6  # HID ErrorRollOver, never silently drop held keys.
    if any(not 0 <= usage <= 101 for usage in usages):
        raise ValueError("Unsupported keyboard usage")
    report = bytes([modifiers & 255, 0] + usages + [0] * (6 - len(usages)))
    return (b"\x01" if combined else b"") + report


def mouse_report(dx=0, dy=0, buttons=0, wheel=0, combined=False):
    clamp = lambda value: max(-127, min(127, int(value))) & 255
    report = bytes([buttons & 7, clamp(dx), clamp(dy), clamp(wheel)])
    return (b"\x03" if combined else b"") + report


def open_node(path):
    """Only selected existing character nodes, with no symlink or file fallback."""
    if not re.fullmatch(r"/dev/hidg[0-9]+", path):
        raise ValueError("Choose an existing /dev/hidgN character device")
    info = os.lstat(path)
    if not stat.S_ISCHR(info.st_mode):
        raise ValueError("HID endpoint is not a character device")
    fd = os.open(path, os.O_WRONLY | os.O_NONBLOCK | os.O_CLOEXEC | os.O_NOFOLLOW)
    actual = os.fstat(fd)
    if (actual.st_dev, actual.st_ino, actual.st_rdev) != (info.st_dev, info.st_ino, info.st_rdev):
        os.close(fd)
        raise ValueError("HID endpoint changed while opening")
    return fd


class Transport:
    def __init__(self, combined=False):
        self.combined = combined
        self.keyboard = None
        self.mouse = None
        self.queue = deque()
        self.started = 0

    def start(self, keyboard_path, mouse_path):
        opened = {}
        try:
            for path in (keyboard_path, mouse_path):
                if path and path not in opened:
                    opened[path] = open_node(path)
            self.keyboard = opened.get(keyboard_path)
            self.mouse = opened.get(mouse_path)
            if self.keyboard is None and self.mouse is None:
                raise ValueError("Choose at least one endpoint")
            if not self.combined and keyboard_path and keyboard_path == mouse_path:
                raise ValueError("Separate boot reports require different keyboard and mouse nodes")
        except Exception:
            for fd in opened.values():
                os.close(fd)
            self.keyboard = self.mouse = None
            raise

    def send(self, kind, report):
        fd = self.keyboard if kind == "keyboard" else self.mouse
        if fd is None:
            return
        if len(self.queue) >= 256:
            raise OSError("HID output queue is full; host may be disconnected")
        if not self.queue:
            self.started = time.monotonic()
        self.queue.append((fd, report))

    def flush(self):
        while self.queue:
            fd, report = self.queue[0]
            try:
                if os.write(fd, report) != len(report):
                    raise OSError("Incomplete HID report")
            except BlockingIOError:
                if time.monotonic() - self.started > 1:
                    raise OSError("Host is not reading HID reports; reconnect and Start again")
                return
            self.queue.popleft()
            self.started = time.monotonic()

    def stop(self):
        self.queue.clear()
        # Best effort release on stop/focus loss; bounded even with a disconnected host.
        releases = []
        if self.keyboard is not None:
            releases.append((self.keyboard, keyboard_report(combined=self.combined)))
        if self.mouse is not None:
            releases.append((self.mouse, mouse_report(combined=self.combined)))
        deadline = time.monotonic() + .2
        try:
            for fd, report in releases:
                while time.monotonic() < deadline:
                    try:
                        os.write(fd, report)
                        break
                    except BlockingIOError:
                        select.select([], [fd], [], max(0, deadline - time.monotonic()))
                    except OSError:
                        break
        finally:
            for fd in set(fd for fd in (self.keyboard, self.mouse) if fd is not None):
                os.close(fd)
            self.keyboard = self.mouse = None


def smoke_test():
    assert ascii_key("a") == (4, 0) and ascii_key("Z") == (29, 2)
    assert ascii_key("1") == (30, 0) and ascii_key("0") == (39, 0)
    assert ascii_key("!") == (30, 2) and ascii_key("?") == (56, 2)
    assert all(ascii_key(chr(i)) is not None for i in range(32, 127))
    assert ascii_key("中") is None
    assert keyboard_report([4, 5], 2) == bytes([2, 0, 4, 5, 0, 0, 0, 0])
    assert keyboard_report(range(4, 11)) == bytes([0, 0, 1, 1, 1, 1, 1, 1])
    assert keyboard_report([4], combined=True) == bytes([1, 0, 0, 4, 0, 0, 0, 0, 0])
    assert mouse_report(-300, 300, 1, -1) == bytes([1, 129, 127, 255])
    assert mouse_report(combined=True) == bytes([3, 0, 0, 0, 0])
    for invalid in ("/tmp/hidg0", "/dev/null", "/dev/hidg0/../hidg1"):
        try:
            open_node(invalid)
            raise AssertionError("unsafe endpoint accepted")
        except ValueError:
            pass
    read_fd, write_fd = os.pipe()
    os.set_blocking(read_fd, False)
    os.set_blocking(write_fd, False)
    transport = Transport()
    transport.keyboard = write_fd
    try:
        transport.send("keyboard", keyboard_report([4]))
        transport.send("keyboard", keyboard_report())
        transport.flush()
        assert os.read(read_fd, 16) == keyboard_report([4]) + keyboard_report()
        transport.stop()
        assert os.read(read_fd, 8) == keyboard_report()
    finally:
        if transport.keyboard is not None:
            transport.stop()
        os.close(read_fd)
    print("hidpilot smoke: PASS (ASCII, modifiers, report layouts, rollover, safe paths, queued input, stop release)")


def run_gui(ui_smoke=False):
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    from gi.repository import Gdk, GLib, Gtk
    GLib.set_prgname("typix-hidpilot")
    GLib.set_application_name("Typix HIDPilot")

    class HIDPilot(Gtk.Window):
        def __init__(self):
            super().__init__(title="HID Keyboard & Mouse")
            self.set_default_size(800, 580)
            self.transport = None
            self.pressed, self.physical_mods = {}, {}
            self.mouse_buttons = 0
            self.last_point = None
            self.sticky = {}
            self.releasing = False
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=9)
            box.set_border_width(14)
            self.add(box)
            description = Gtk.Label(label="Control a connected host using already configured USB HID endpoints.")
            description.set_xalign(0)
            description.set_line_wrap(True)
            box.pack_start(description, False, False, 0)
            row = Gtk.Box(spacing=8)
            box.pack_start(row, False, False, 0)
            self.keyboard_node, self.mouse_node = Gtk.ComboBoxText(), Gtk.ComboBoxText()
            for label, control in (("Keyboard", self.keyboard_node), ("Mouse", self.mouse_node)):
                row.pack_start(Gtk.Label(label=label), False, False, 0)
                row.pack_start(control, True, True, 0)
            refresh = Gtk.Button(label="Refresh")
            refresh.connect("clicked", self.refresh)
            row.pack_start(refresh, False, False, 0)
            row = Gtk.Box(spacing=8)
            box.pack_start(row, False, False, 0)
            self.profile = Gtk.ComboBoxText()
            self.profile.append_text("Boot keyboard (8 B) + relative mouse (4 B)")
            self.profile.append_text("C1Max combined IDs: keyboard 1 / relative mouse 3")
            self.profile.set_active(0)
            row.pack_start(self.profile, True, True, 0)
            self.start_button = Gtk.Button(label="Start")
            self.start_button.connect("clicked", self.start_stop)
            row.pack_start(self.start_button, False, False, 0)
            self.confirm = Gtk.CheckButton(label="These selected nodes use the report layout above.")
            self.confirm.connect("toggled", lambda *_: self.update_start())
            box.pack_start(self.confirm, False, False, 0)
            self.pad = Gtk.DrawingArea()
            self.pad.set_can_focus(True)
            self.pad.set_size_request(300, 180)
            self.pad.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK |
                                Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.SCROLL_MASK |
                                Gdk.EventMask.SMOOTH_SCROLL_MASK)
            self.pad.connect("draw", self.draw_pad)
            self.pad.connect("button-press-event", self.pad_event)
            self.pad.connect("button-release-event", self.pad_event)
            self.pad.connect("motion-notify-event", self.pad_event)
            self.pad.connect("scroll-event", self.scroll)
            box.pack_start(self.pad, True, True, 0)
            row = Gtk.Box(spacing=8)
            box.pack_start(row, False, False, 0)
            for label, mask in (("Left mouse", 1), ("Right mouse", 2)):
                button = Gtk.Button(label=label)
                button.connect("pressed", self.mouse_down, mask)
                button.connect("released", self.mouse_up, mask)
                row.pack_start(button, True, True, 0)
            for label, direction in (("Scroll ↑", 1), ("Scroll ↓", -1)):
                button = Gtk.Button(label=label)
                button.connect("clicked", lambda _button, value=direction: self.send_mouse(wheel=value))
                row.pack_start(button, True, True, 0)
            row = Gtk.Box(spacing=6)
            box.pack_start(row, False, False, 0)
            for label, mask in (("Ctrl", 1), ("Shift", 2), ("Alt", 4), ("Super", 8)):
                control = Gtk.ToggleButton(label=label)
                control.connect("toggled", lambda *_: self.send_keyboard())
                self.sticky[mask] = control
                row.pack_start(control, True, True, 0)
            for label, usage in (("Esc", 41), ("Tab", 43), ("←", 80), ("→", 79), ("Enter", 40)):
                control = Gtk.Button(label=label)
                control.connect("pressed", self.touch_key_down, usage)
                control.connect("released", self.touch_key_up, usage)
                row.pack_start(control, True, True, 0)
            row = Gtk.Box(spacing=8)
            box.pack_start(row, False, False, 0)
            self.capture = Gtk.CheckButton(label="Forward physical keyboard while this window is focused")
            self.capture.connect("toggled", self.capture_changed)
            row.pack_start(self.capture, True, True, 0)
            release = Gtk.Button(label="Release all · Esc")
            release.connect("clicked", self.release)
            row.pack_start(release, False, False, 0)
            self.status = Gtk.Label(label="")
            self.status.set_line_wrap(True)
            self.status.set_xalign(0)
            box.pack_start(self.status, False, False, 0)
            self.connect("key-press-event", self.key)
            self.connect("key-release-event", self.key)
            self.connect("focus-out-event", self.focus_lost)
            self.connect("destroy", self.close)
            self.refresh()
            self.timer = GLib.timeout_add(16, self.flush)
            self.show_all()

        def refresh(self, *_):
            if self.transport:
                return
            nodes = []
            for path in sorted(glob.glob("/dev/hidg[0-9]*")):
                try:
                    if stat.S_ISCHR(os.lstat(path).st_mode):
                        nodes.append(path)
                except OSError:
                    pass
            for control in (self.keyboard_node, self.mouse_node):
                control.remove_all()
                control.append("", "Disabled")
                for node in nodes:
                    control.append(node, node)
                control.set_active(0)
            if nodes:
                self.keyboard_node.set_active(1)
                if len(nodes) > 1:
                    self.mouse_node.set_active(2)
                self.status.set_text("Choose nodes and the matching report layout, confirm, then Start. F12 always stops forwarding.")
            else:
                self.status.set_text("Hardware unavailable: no /dev/hidg endpoints. USB gadget support must be configured separately by an administrator. This app does not change USB mode, load modules or use root.")
            self.confirm.set_active(False)
            self.update_start()

        def update_start(self):
            any_node = bool(self.keyboard_node.get_active_id() or self.mouse_node.get_active_id())
            self.start_button.set_sensitive(bool(self.transport) or (any_node and self.confirm.get_active()))

        def start_stop(self, *_):
            if self.transport:
                self.stop()
                self.status.set_text("Stopped. Inputs released; gadget configuration is unchanged.")
                return
            if not self.confirm.get_active() or ui_smoke:
                return
            transport = Transport(combined=self.profile.get_active() == 1)
            try:
                transport.start(self.keyboard_node.get_active_id(), self.mouse_node.get_active_id())
                self.transport = transport
                self.start_button.set_label("Stop · F12")
                for control in (self.keyboard_node, self.mouse_node, self.profile, self.confirm):
                    control.set_sensitive(False)
                self.status.set_text("Connected · drag touchpad to move, tap to click. Enable physical keyboard forwarding if wanted. F12 stops.")
                self.release()
            except (OSError, ValueError) as error:
                transport.stop()
                self.status.set_text(f"Cannot start: {error}. Check node permissions and the USB host, then retry.")

        def send(self, kind, report):
            if self.transport:
                try:
                    self.transport.send(kind, report)
                    self.transport.flush()
                except OSError as error:
                    self.stop()
                    self.status.set_text(f"USB stopped: {error}. Reconnect the host and Start again.")

        def send_keyboard(self):
            if self.releasing or not self.transport:
                return
            modifiers = 0
            for value in self.physical_mods.values():
                modifiers |= value
            for mask, control in self.sticky.items():
                if control.get_active():
                    modifiers |= mask
            for _usage, shift in self.pressed.values():
                modifiers |= shift
            self.send("keyboard", keyboard_report([usage for usage, _mods in self.pressed.values()], modifiers,
                                                   self.transport.combined))

        def send_mouse(self, dx=0, dy=0, wheel=0):
            if self.transport:
                self.send("mouse", mouse_report(dx, dy, self.mouse_buttons, wheel, self.transport.combined))

        def touch_key_down(self, _button, usage):
            self.pressed[("touch", usage)] = usage, 0
            self.send_keyboard()

        def touch_key_up(self, _button, usage):
            self.pressed.pop(("touch", usage), None)
            self.send_keyboard()

        def mouse_down(self, _button, mask):
            self.mouse_buttons |= mask
            self.send_mouse()

        def mouse_up(self, _button, mask):
            self.mouse_buttons &= ~mask
            self.send_mouse()

        def capture_changed(self, *_):
            self.release()
            if self.capture.get_active():
                self.pad.grab_focus()

        def release(self, *_):
            self.releasing = True
            self.pressed.clear()
            self.physical_mods.clear()
            self.mouse_buttons = 0
            self.last_point = None
            for control in self.sticky.values():
                control.set_active(False)
            self.releasing = False
            self.send_keyboard()
            self.send_mouse()
            return False

        def focus_lost(self, *_):
            self.release()
            self.capture.set_active(False)
            return False

        def stop(self):
            # Detach first so UI reset does not enqueue further input.
            transport, self.transport = self.transport, None
            if transport:
                transport.stop()
            self.release()
            self.capture.set_active(False)
            self.start_button.set_label("Start")
            for control in (self.keyboard_node, self.mouse_node, self.profile, self.confirm):
                control.set_sensitive(True)
            self.update_start()

        def flush(self):
            if self.transport:
                try:
                    self.transport.flush()
                except OSError as error:
                    self.stop()
                    self.status.set_text(f"USB stopped: {error}")
            return True

        def key(self, _widget, event):
            name = Gdk.keyval_name(event.keyval)
            down = event.type == Gdk.EventType.KEY_PRESS
            if name == "F12":
                if down:
                    self.stop()
                    self.status.set_text("Stopped with F12. Inputs released.")
                return True
            if name == "Escape":
                if down:
                    self.release()
                    self.capture.set_active(False)
                return True
            if not self.transport or not self.capture.get_active():
                return False
            source = ("key", event.hardware_keycode)
            if not down:
                self.pressed.pop(source, None)
                self.physical_mods.pop(source, None)
            elif name in MODIFIERS:
                self.physical_mods[source] = MODIFIERS[name]
            else:
                value = Gdk.keyval_to_unicode(event.keyval)
                mapping = ascii_key(chr(value)) if value else None
                if name in SPECIAL:
                    mapping = SPECIAL[name], 0
                if mapping:
                    self.pressed[source] = mapping
                else:
                    self.status.set_text("Only US ASCII keyboard usages are supported; choose an input method on the host for other languages.")
            self.send_keyboard()
            return True

        def pad_event(self, _widget, event):
            if event.type == Gdk.EventType.BUTTON_PRESS and event.button == 1:
                self.last_point = event.x, event.y
                self.tap_origin = event.x, event.y, time.monotonic()
                self.moved = False
                self.pad.grab_focus()
            elif event.type == Gdk.EventType.MOTION_NOTIFY and self.last_point:
                dx, dy = event.x - self.last_point[0], event.y - self.last_point[1]
                self.last_point = event.x, event.y
                if abs(event.x - self.tap_origin[0]) + abs(event.y - self.tap_origin[1]) > 5:
                    self.moved = True
                self.send_mouse(dx=dx, dy=dy)
            elif event.type == Gdk.EventType.BUTTON_RELEASE and self.last_point:
                if not self.moved and time.monotonic() - self.tap_origin[2] < .6:
                    self.mouse_down(None, 1)
                    self.mouse_up(None, 1)
                self.last_point = None
            return True

        def scroll(self, _widget, event):
            if event.direction == Gdk.ScrollDirection.UP:
                self.send_mouse(wheel=1)
            elif event.direction == Gdk.ScrollDirection.DOWN:
                self.send_mouse(wheel=-1)
            elif event.direction == Gdk.ScrollDirection.SMOOTH:
                _ok, _dx, dy = event.get_scroll_deltas()
                if abs(dy) >= .1:
                    self.send_mouse(wheel=-1 if dy > 0 else 1)
            return True

        def draw_pad(self, widget, context):
            context.set_source_rgb(.10, .13, .17)
            context.paint()
            context.set_source_rgb(.78, .84, .9)
            context.set_font_size(18)
            context.move_to(24, widget.get_allocated_height() / 2)
            context.show_text("Touchpad · drag to move, tap to click")

        def close(self, *_):
            GLib.source_remove(self.timer)
            self.stop()
            Gtk.main_quit()

    window = HIDPilot()
    if not ui_smoke and os.environ.get("TYPIX_WINDOWED") != "1":
        window.fullscreen()
    if ui_smoke:
        if os.environ.get("C1MAX_UI_SCREENSHOT"):
            def screenshot():
                Gdk.pixbuf_get_from_window(window.get_window(), 0, 0, window.get_allocated_width(),
                                          window.get_allocated_height()).savev(os.environ["C1MAX_UI_SCREENSHOT"], "png", [], [])
                return False
            GLib.timeout_add(650, screenshot)
        GLib.timeout_add(1000, lambda: (window.destroy(), False)[1])
    Gtk.main()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--ui-smoke-test", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.smoke_test:
            smoke_test()
        else:
            run_gui(args.ui_smoke_test)
    except (ImportError, ValueError, RuntimeError) as error:
        print(f"HIDPilot: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

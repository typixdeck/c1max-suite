#!/usr/bin/python3
"""GTK/V4L2 instant camera; source and artwork attribution in README.md."""
import argparse
import datetime
import fcntl
from functools import lru_cache
import glob
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import sys
import tempfile
import threading
import time

RATIOS = {"4:3": (4, 3), "3:4": (3, 4), "1:1": (1, 1), "16:9": (16, 9)}
FILTERS = ("Original", "Mono", "Sepia", "Warm", "Cool", "Faded")
PAPERS = ("None", "White", "Cream", "Film")
ASSETS = Path(__file__).resolve().parent / "assets" / "frames"
MAX_PIXELS = 4096 * 4096
MAX_BYTES = 32 * 1024 * 1024


@lru_cache(maxsize=3)
def frame_asset(name):
    from PIL import Image
    sw, sh, l, t, r, b = map(int, (ASSETS / f"{name}.window").read_text().split())
    with Image.open(ASSETS / f"{name}.png") as original:
        if original.size != (sw, sh):
            raise ValueError("Frame artwork and aperture dimensions disagree")
        frame = original.convert("RGBA")
        frame.thumbnail((512, 512), Image.Resampling.LANCZOS)
    l, r = l * frame.width // sw, r * frame.width // sw
    t, b = t * frame.height // sh, b * frame.height // sh
    return frame, (0, l, r, frame.width), (0, t, b, frame.height)


def data_dir():
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))) / "c1max-camera"


def discover_devices():
    """Query only V4L2 capture capabilities; never change a device's controls."""
    devices = []
    for path in sorted(glob.glob("/dev/video[0-9]*")):
        fd = None
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
            raw = bytearray(104)
            fcntl.ioctl(fd, 0x80685600, raw)  # VIDIOC_QUERYCAP, struct v4l2_capability
            _driver, card, _bus, _version, caps, device_caps, *_reserved = struct.unpack("16s32s32sIIIIII", raw)
            effective = device_caps if caps & 0x80000000 else caps
            if effective & (0x1 | 0x1000) and effective & (0x04000000 | 0x01000000):
                name = card.split(b"\0", 1)[0].decode("utf-8", "replace")
                devices.append((path, name or Path(path).name))
        except (OSError, ValueError):
            pass
        finally:
            if fd is not None:
                os.close(fd)
    return devices


def compose(image, ratio="4:3", look="Original", paper="None", rotation=0, max_edge=1600):
    from PIL import Image, ImageEnhance, ImageOps
    result = image.convert("RGB")
    if rotation:
        result = result.rotate(-rotation, expand=True)
    rw, rh = RATIOS[ratio]
    width, height = result.size
    if width * rh > height * rw:
        cropped = (height * rw // rh, height)
    else:
        cropped = (width, width * rh // rw)
    left, top = (width - cropped[0]) // 2, (height - cropped[1]) // 2
    result = result.crop((left, top, left + cropped[0], top + cropped[1]))
    result.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    if look == "Mono":
        result = ImageOps.grayscale(result).convert("RGB")
    elif look == "Sepia":
        result = ImageOps.colorize(ImageOps.grayscale(result), "#21190f", "#ffe7ba")
    elif look in ("Warm", "Cool"):
        r, g, b = result.split()
        offsets = (14, 2, -10) if look == "Warm" else (-10, 2, 14)
        result = Image.merge("RGB", tuple(channel.point(lambda x, offset=offset: max(0, min(255, x + offset)))
                                           for channel, offset in zip((r, g, b), offsets)))
    elif look == "Faded":
        result = ImageEnhance.Color(ImageEnhance.Contrast(result).enhance(.78)).enhance(.68)
        result = Image.blend(result, Image.new("RGB", result.size, "#ddc7a2"), .12)
        # A small radial mask is resized in C; avoid per-pixel Python work on each preview.
        mask = Image.new("L", (64, 64))
        mask.putdata([int(max(0, 1 - ((x - 31.5) ** 2 + (y - 31.5) ** 2) / 1984) * 90 + 165)
                      for y in range(64) for x in range(64)])
        mask = mask.resize(result.size, Image.Resampling.BILINEAR)
        result = Image.composite(result, Image.new("RGB", result.size, "#1c1713"), mask)
    if paper == "None":
        return result
    width, height = result.size
    edge = max(8, min(width, height) // 10)
    bottom = edge if paper == "Film" else edge * 3
    size = (width + 2 * edge, height + edge + bottom)
    matte = Image.new("RGBA", size, "#16171a")
    name = paper.lower()
    frame, sx, sy = frame_asset(name)
    dx, dy = (0, edge, edge + width, size[0]), (0, edge, edge + height, size[1])
    for row in range(3):
        for column in range(3):
            if row == column == 1:
                continue
            patch = frame.crop((sx[column], sy[row], sx[column + 1], sy[row + 1]))
            patch = patch.resize((dx[column + 1] - dx[column], dy[row + 1] - dy[row]), Image.Resampling.BILINEAR)
            matte.alpha_composite(patch, (dx[column], dy[row]))
    matte.paste(result, (edge, edge))
    return matte.convert("RGB")


def save_photo(image, directory, cancelled=None):
    """Publish only fully synced JPEGs; cancellation leaves no partial photo."""
    directory = Path(directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if shutil.disk_usage(directory).free < MAX_BYTES:
        raise OSError("Not enough free space; at least 32 MiB is required")
    fd, temporary = tempfile.mkstemp(prefix=".capture-", suffix=".jpg", dir=directory)
    path = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as stream:
            image.save(stream, format="JPEG", quality=92)
            stream.flush()
            os.fsync(stream.fileno())
        if cancelled and cancelled.is_set():
            raise InterruptedError("Capture cancelled")
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        target = directory / f"print-{stamp}-{path.stem.removeprefix('.capture-')}.jpg"
        # Link refuses collisions and publishes an already-complete inode atomically.
        os.link(path, target)
        path.unlink()
        dfd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
        return target
    finally:
        path.unlink(missing_ok=True)


def album_files(directory):
    paths = []
    for path in Path(directory).glob("*.jpg"):
        try:
            info = path.lstat()
            if stat.S_ISREG(info.st_mode) and 0 < info.st_size <= MAX_BYTES:
                paths.append((info.st_mtime_ns, path))
        except OSError:
            pass
    return [path for _time, path in sorted(paths, reverse=True)]


def read_photo(path):
    from PIL import Image, ImageOps
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_BYTES:
            raise ValueError("Photo is not a regular JPEG within 32 MiB")
        try:
            with Image.open(stream) as image:
                if image.format != "JPEG" or image.width * image.height > MAX_PIXELS:
                    raise ValueError("Photo exceeds supported JPEG dimensions")
                return ImageOps.exif_transpose(image).convert("RGB"), (info.st_dev, info.st_ino, info.st_mtime_ns, info.st_size)
        except Image.DecompressionBombError as error:
            raise ValueError("Photo exceeds supported JPEG dimensions") from error


def delete_photo(path, expected, directory):
    path, directory = Path(path), Path(directory)
    if path.parent.resolve() != directory.resolve() or path.suffix.lower() != ".jpg":
        raise ValueError("Photo must belong to this album")
    info = path.lstat()
    actual = info.st_dev, info.st_ino, info.st_mtime_ns, info.st_size
    if not stat.S_ISREG(info.st_mode) or actual != expected:
        raise ValueError("Photo changed since it was displayed; reopen it before deleting")
    path.unlink()


def smoke_test():
    from PIL import Image
    from unittest.mock import patch
    sample = Image.new("RGB", (96, 72), (100, 160, 220))
    for ratio in RATIOS:
        for look in FILTERS:
            for paper in PAPERS:
                result = compose(sample, ratio, look, paper)
                assert result.width > 0 and result.height > 0 and result.mode == "RGB"
                if paper == "None":
                    rw, rh = RATIOS[ratio]
                    assert abs(result.width * rh - result.height * rw) < max(rw, rh)
                if paper != "None" and look == "Original":
                    assert result.getpixel((result.width // 2, result.height // 2)) == (100, 160, 220)
    plain = compose(sample, "1:1")
    assert plain.size == (72, 72) and plain.getpixel((36, 36)) == (100, 160, 220)
    with tempfile.TemporaryDirectory(prefix="c1-camera-test-") as directory:
        path = save_photo(plain, directory)
        assert path.stat().st_mode & 0o777 == 0o600
        image, identity = read_photo(path)
        assert image.size == plain.size and album_files(directory) == [path]
        with patch("shutil.disk_usage", return_value=shutil._ntuple_diskusage(MAX_BYTES, MAX_BYTES, 0)):
            try:
                save_photo(plain, directory)
                raise AssertionError("low-space capture was accepted")
            except OSError:
                pass
        try:
            delete_photo(path, (0, 0, 0, 0), directory)
            raise AssertionError("changed photo was accepted")
        except ValueError:
            pass
        cancelled = threading.Event()
        cancelled.set()
        try:
            save_photo(plain, directory, cancelled)
            raise AssertionError("cancelled capture was published")
        except InterruptedError:
            pass
        link = Path(directory) / "symlink.jpg"
        link.symlink_to(path)
        assert album_files(directory) == [path]
        try:
            delete_photo(link, identity, directory)
            raise AssertionError("symlink was accepted")
        except ValueError:
            pass
        delete_photo(path, identity, directory)
        assert not album_files(directory)
        assert not list(Path(directory).glob(".capture-*"))
    print("camera smoke: PASS (96 compositions, crop/frame pixels, JPEG, private atomic save, low space, cancellation, album, safe deletion)")


def run_gui(ui_smoke=False):
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    gi.require_version("Gst", "1.0")
    gi.require_version("GstVideo", "1.0")
    from gi.repository import Gdk, GdkPixbuf, GLib, Gst, GstVideo, Gtk
    GLib.set_prgname("typix-camera")
    GLib.set_application_name("Typix Camera")
    from PIL import Image
    Gst.init(None)

    class Camera(Gtk.Window):
        def __init__(self):
            super().__init__(title="Instant Camera")
            self.set_default_size(800, 600)
            self.pipeline = None
            self.shutter_audio = None
            self.flash_until = 0
            self.raw, self.raw_lock = None, threading.Lock()
            self.frame_time, self.display_time = 0, 0
            self.album = False
            self.paths, self.index, self.identity = [], 0, None
            self.saving, self.closing = False, False
            self.ui_verified = False
            self.cancelled = threading.Event()
            self.root = data_dir()
            if ui_smoke:
                self.temp_root = tempfile.TemporaryDirectory(prefix="c1-camera-ui-")
                self.root = Path(self.temp_root.name)
            self.photos = self.root / "photos"
            try:
                self.settings = json.loads((self.root / "settings.json").read_text())
            except (OSError, ValueError):
                self.settings = {}
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            box.set_border_width(12)
            self.add(box)
            row = Gtk.Box(spacing=8)
            box.pack_start(row, False, False, 0)
            self.device = Gtk.ComboBoxText()
            row.pack_start(self.device, True, True, 0)
            refresh = Gtk.Button(label="Refresh devices")
            refresh.connect("clicked", self.refresh)
            row.pack_start(refresh, False, False, 0)
            self.start_button = Gtk.Button(label="Start / Retry")
            self.start_button.connect("clicked", self.start)
            row.pack_start(self.start_button, False, False, 0)
            self.preview = Gtk.DrawingArea()
            self.preview.set_size_request(320, 220)
            self.preview.connect("draw", self.draw)
            self.pixbuf = None
            box.pack_start(self.preview, True, True, 0)
            row = Gtk.Box(spacing=8)
            box.pack_start(row, False, False, 0)
            self.choices = {}
            for label, options, default in (("Ratio", list(RATIOS), "4:3"), ("Filter", FILTERS, "Original"),
                                             ("Paper", PAPERS, "None"), ("Rotate", ("0", "90", "180", "270"), "0")):
                row.pack_start(Gtk.Label(label=label), False, False, 0)
                choice = Gtk.ComboBoxText()
                for option in options:
                    choice.append_text(option)
                value = str(self.settings.get(label, default))
                choice.set_active(list(options).index(value) if value in options else 0)
                choice.connect("changed", self.changed)
                self.choices[label] = choice
                row.pack_start(choice, True, True, 0)
            row = Gtk.Box(spacing=8)
            box.pack_start(row, False, False, 0)
            self.shutter = Gtk.Button(label="Take photo · Space")
            self.shutter.connect("clicked", self.capture)
            row.pack_start(self.shutter, True, True, 0)
            self.album_button = Gtk.Button(label="Album · G")
            self.album_button.connect("clicked", self.toggle_album)
            row.pack_start(self.album_button, False, False, 0)
            self.previous = Gtk.Button(label="◀")
            self.previous.connect("clicked", lambda *_: self.browse(-1))
            row.pack_start(self.previous, False, False, 0)
            self.next = Gtk.Button(label="▶")
            self.next.connect("clicked", lambda *_: self.browse(1))
            row.pack_start(self.next, False, False, 0)
            self.delete = Gtk.Button(label="Delete")
            self.delete.connect("clicked", self.confirm_delete)
            row.pack_start(self.delete, False, False, 0)
            self.status = Gtk.Label(label="Choose a supported V4L2 camera, then Start.")
            self.status.set_line_wrap(True)
            self.status.set_xalign(0)
            self.status.set_selectable(True)
            box.pack_start(self.status, False, False, 0)
            self.connect("key-press-event", self.key)
            self.connect("destroy", self.close)
            self.refresh()
            self.show_all()
            self.update_buttons()
            self.timer = GLib.timeout_add(100, self.update)

        def update_buttons(self):
            for button in (self.previous, self.next, self.delete):
                button.set_sensitive(self.album and bool(self.paths))
            self.shutter.set_label("Cancel capture" if self.saving else "Take photo · Space")
            self.shutter.set_sensitive(not self.album)
            self.album_button.set_label("Back to camera · G" if self.album else "Album · G")
            self.album_button.set_sensitive(not self.saving)
            for control in [self.device, self.start_button, *self.choices.values()]:
                control.set_sensitive(not self.album and not self.saving)

        def refresh(self, *_):
            if self.pipeline or self.saving:
                return
            self.device.remove_all()
            devices = [("test", "Isolated test pattern")] if ui_smoke else discover_devices()
            for path, name in devices:
                self.device.append(path, f"{name} ({path})")
            if devices:
                self.device.set_active(0)
            else:
                self.status.set_text("No accessible V4L2 camera. Connect a USB camera or check video-group permissions, then Refresh. CSI cameras must expose a compatible V4L2 capture node.")

        def parameters(self):
            return dict(ratio=self.choices["Ratio"].get_active_text(), look=self.choices["Filter"].get_active_text(),
                        paper=self.choices["Paper"].get_active_text(), rotation=int(self.choices["Rotate"].get_active_text()))

        def changed(self, *_):
            self.display_time = 0
            try:
                self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
                values = {name: control.get_active_text() for name, control in self.choices.items()}
                fd, temporary = tempfile.mkstemp(prefix=".settings-", dir=self.root)
                try:
                    with os.fdopen(fd, "w") as output:
                        json.dump(values, output)
                    os.replace(temporary, self.root / "settings.json")
                finally:
                    Path(temporary).unlink(missing_ok=True)
            except OSError as error:
                self.status.set_text(f"Settings could not be saved: {error}")

        def start(self, *_):
            if self.saving or self.album:
                return
            self.stop()
            path = self.device.get_active_id()
            if not path:
                self.refresh()
                return
            try:
                source = "videotestsrc is-live=true" if path == "test" else "v4l2src name=camera"
                # decodebin accepts both raw and compressed UVC formats.
                pipeline = Gst.parse_launch(source + " ! decodebin ! videoconvert ! video/x-raw,format=RGB "
                                            "! appsink name=frames emit-signals=true max-buffers=1 drop=true sync=false")
                if path != "test":
                    pipeline.get_by_name("camera").set_property("device", path)
                self.pipeline = pipeline
                pipeline.get_by_name("frames").connect("new-sample", self.sample)
                bus = pipeline.get_bus()
                bus.add_signal_watch()
                bus.connect("message::error", self.pipeline_error)
                bus.connect("message::eos", self.pipeline_eos)
                self.frame_time = time.monotonic()
                if pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
                    raise RuntimeError("Camera pipeline could not start")
                self.status.set_text("Starting camera…")
            except Exception as error:
                self.stop()
                self.status.set_text(f"Camera unavailable: {error}. Close other camera apps and use Start / Retry.")

        def sample(self, sink):
            sample = sink.emit("pull-sample")
            if sample is None:
                return Gst.FlowReturn.ERROR
            info = GstVideo.VideoInfo.new_from_caps(sample.get_caps())
            if not info or info.width * info.height > MAX_PIXELS or info.width < 1 or info.height < 1:
                return Gst.FlowReturn.ERROR
            buffer = sample.get_buffer()
            ok, mapped = buffer.map(Gst.MapFlags.READ)
            if not ok:
                return Gst.FlowReturn.ERROR
            try:
                frame = Image.frombytes("RGB", (info.width, info.height), bytes(mapped.data), "raw", "RGB", info.stride[0])
                with self.raw_lock:
                    self.raw = frame
                    self.frame_time = time.monotonic()
            except (ValueError, OSError):
                return Gst.FlowReturn.ERROR
            finally:
                buffer.unmap(mapped)
            return Gst.FlowReturn.OK

        def stop(self):
            if self.pipeline:
                self.pipeline.set_state(Gst.State.NULL)
                self.pipeline.get_bus().remove_signal_watch()
                self.pipeline = None
            with self.raw_lock:
                self.raw = None

        def pipeline_error(self, _bus, message):
            error, _debug = message.parse_error()
            self.stop()
            self.status.set_text(f"Camera error: {error.message}. Use Start / Retry.")

        def pipeline_eos(self, *_):
            self.stop()
            self.status.set_text("Camera disconnected or stopped. Use Start / Retry.")

        def update(self):
            if self.closing:
                return False
            if self.flash_until:
                self.preview.queue_draw()
                if time.monotonic() >= self.flash_until:
                    self.flash_until = 0
            if self.pipeline and not self.album:
                if time.monotonic() - self.frame_time > 5:
                    self.stop()
                    self.status.set_text("No camera frame for five seconds. Check the camera and use Start / Retry.")
                else:
                    with self.raw_lock:
                        raw = self.raw
                        frame_time = self.frame_time
                    if raw is not None and frame_time > self.display_time:
                        try:
                            result = compose(raw, **self.parameters(), max_edge=700)
                            self.display(result)
                            if self.display_time == 0:
                                self.status.set_text(f"Live · {raw.width} × {raw.height} · Space takes a photo")
                            self.display_time = frame_time
                        except (OSError, ValueError) as error:
                            self.stop()
                            self.status.set_text(f"Preview failed: {error}")
            return True

        def display(self, image):
            image = image.copy()
            image.thumbnail((1200, 900))
            raw = GLib.Bytes.new(image.tobytes())
            self.pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(raw, GdkPixbuf.Colorspace.RGB, False, 8,
                                                       image.width, image.height, image.width * 3)
            self.preview.queue_draw()

        def draw(self, widget, context):
            context.set_source_rgb(.055, .06, .07)
            context.paint()
            if self.pixbuf:
                w, h = widget.get_allocated_width(), widget.get_allocated_height()
                scale = min(w / self.pixbuf.get_width(), h / self.pixbuf.get_height())
                context.translate((w - self.pixbuf.get_width() * scale) / 2, (h - self.pixbuf.get_height() * scale) / 2)
                context.scale(scale, scale)
                Gdk.cairo_set_source_pixbuf(context, self.pixbuf, 0, 0)
                context.paint()
            if self.flash_until > time.monotonic():
                context.set_source_rgba(1, 1, 1, min(1, (self.flash_until - time.monotonic()) / .18))
                context.paint()

        def capture(self, *_):
            if self.album:
                return
            if self.saving:
                self.cancelled.set()
                self.status.set_text("Cancelling capture…")
                return
            with self.raw_lock:
                raw = self.raw.copy() if self.raw is not None else None
            if raw is None:
                self.start()
                return
            self.saving = True
            self.cancelled.clear()
            parameters = self.parameters()
            self.update_buttons()
            self.status.set_text("Saving photo…")
            def worker():
                try:
                    photo = compose(raw, **parameters)
                    path = save_photo(photo, self.photos, self.cancelled)
                    message = f"Saved {path.name} · Album opens your photos"
                except InterruptedError:
                    message = "Capture cancelled"
                except (OSError, ValueError) as error:
                    message = f"Capture failed: {error}"
                GLib.idle_add(self.saved, message)
            self.worker = threading.Thread(target=worker, name="camera-save", daemon=False)
            self.worker.start()

        def saved(self, message):
            self.saving = False
            if not self.closing:
                self.status.set_text(message)
                if message.startswith("Saved "):
                    self.flash_until = time.monotonic() + .18
                    self.preview.queue_draw()
                    self.play_shutter()
                self.update_buttons()
            return False

        def play_shutter(self):
            if ui_smoke:
                return
            self.stop_shutter()
            sound = ASSETS.parent / "shutter.wav"
            if sound.is_file():
                self.shutter_audio = Gst.ElementFactory.make("playbin", None)
                if self.shutter_audio:
                    self.shutter_audio.set_property("uri", sound.as_uri())
                    self.shutter_audio.set_state(Gst.State.PLAYING)
                    GLib.timeout_add(1500, self.stop_shutter)

        def stop_shutter(self):
            if self.shutter_audio:
                self.shutter_audio.set_state(Gst.State.NULL)
                self.shutter_audio = None
            return False

        def toggle_album(self, *_):
            if self.saving:
                return
            self.album = not self.album
            if self.album:
                self.stop()
                self.paths = album_files(self.photos)
                self.index = 0
                self.show_photo()
            else:
                self.start()
            self.update_buttons()

        def show_photo(self):
            self.identity = None
            self.pixbuf = None
            if not self.paths:
                self.status.set_text(f"No photos yet · {self.photos}")
            else:
                path = self.paths[self.index]
                try:
                    image, self.identity = read_photo(path)
                    self.display(image)
                    if ui_smoke:
                        self.ui_verified = True
                    self.status.set_text(f"{self.index + 1}/{len(self.paths)} · {path.name}")
                except (OSError, ValueError) as error:
                    self.status.set_text(f"Cannot open {path.name}: {error}")
            self.preview.queue_draw()
            self.update_buttons()

        def browse(self, direction):
            if self.album and self.paths:
                self.index = (self.index + direction) % len(self.paths)
                self.show_photo()

        def confirm_delete(self, *_):
            if not self.album or not self.paths or self.identity is None:
                return
            path, expected = self.paths[self.index], self.identity
            dialog = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.QUESTION,
                                       buttons=Gtk.ButtonsType.CANCEL, text="Delete this photo?")
            dialog.format_secondary_text(path.name)
            dialog.add_button("Delete", Gtk.ResponseType.ACCEPT)
            response = dialog.run()
            dialog.destroy()
            if response != Gtk.ResponseType.ACCEPT:
                return
            try:
                delete_photo(path, expected, self.photos)
                self.paths = album_files(self.photos)
                self.index = min(self.index, max(0, len(self.paths) - 1))
                self.show_photo()
            except (OSError, ValueError) as error:
                self.status.set_text(f"Delete failed: {error}")

        def key(self, _widget, event):
            key = Gdk.keyval_name(event.keyval)
            if key == "Escape":
                if self.album:
                    self.toggle_album()
                elif self.saving:
                    self.cancelled.set()
                else:
                    self.destroy()
            elif key in ("g", "G"):
                self.toggle_album()
            elif key == "space":
                self.toggle_album() if self.album else self.capture()
            elif self.album and key in ("Left", "a", "Right", "d"):
                self.browse(-1 if key in ("Left", "a") else 1)
            elif self.album and key in ("Delete", "BackSpace", "x"):
                self.confirm_delete()
            elif not self.album and key in ("r", "f", "b"):
                choice = self.choices[{"r": "Ratio", "f": "Filter", "b": "Paper"}[key]]
                choice.set_active((choice.get_active() + 1) % len(choice.get_model()))
            else:
                return False
            return True

        def close(self, *_):
            self.closing = True
            self.cancelled.set()
            self.stop()
            self.stop_shutter()
            if self.saving:
                self.worker.join(timeout=5)
            GLib.source_remove(self.timer)
            if ui_smoke:
                self.temp_root.cleanup()
            Gtk.main_quit()

    window = Camera()
    if not ui_smoke and os.environ.get("TYPIX_WINDOWED") != "1":
        window.fullscreen()
    if ui_smoke:
        if os.environ.get("C1MAX_UI_SCREENSHOT"):
            def screenshot():
                Gdk.pixbuf_get_from_window(window.get_window(), 0, 0, window.get_allocated_width(),
                                          window.get_allocated_height()).savev(os.environ["C1MAX_UI_SCREENSHOT"], "png", [], [])
                return False
            GLib.timeout_add(650, screenshot)
        GLib.timeout_add(100, lambda: (window.start(), False)[1])
        def choose_composition():
            window.choices["Ratio"].set_active(2)
            window.choices["Filter"].set_active(2)
            window.choices["Paper"].set_active(1)
            return False
        GLib.timeout_add(300, choose_composition)
        GLib.timeout_add(1000, lambda: (window.capture(), False)[1])
        GLib.timeout_add(1800, lambda: (window.toggle_album(), False)[1])
        GLib.timeout_add(2300, lambda: (window.destroy(), False)[1])
    Gtk.main()
    if ui_smoke and not window.ui_verified:
        raise RuntimeError("Synthetic camera preview → capture → JPEG album verification failed")


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
        print(f"Camera: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

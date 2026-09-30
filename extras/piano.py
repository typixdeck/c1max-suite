#!/usr/bin/python3
"""Native GTK piano, informed by C1Max apps/piano; see README.md."""
import argparse
import array
import math
import os
import sys
import threading

RATE = 24000
KEYS = dict(zip("zsxdcvgbhnjmq2w3er5t6y7u", range(60, 84)))
WHITE = [60, 62, 64, 65, 67, 69, 71, 72, 74, 76, 77, 79, 81, 83]
BLACK = [(61, 0), (63, 1), (66, 3), (68, 4), (70, 5),
         (73, 7), (75, 8), (78, 10), (80, 11), (82, 12)]
AUDIO_PIPELINE = ("appsrc name=synth is-live=true format=time block=true max-bytes=1920 "
                  "caps=audio/x-raw,format=S16LE,rate=24000,channels=1,layout=interleaved "
                  "! audioconvert ! audioresample ! autoaudiosink")


class Synth:
    """24 independent oscillators with 4 ms attack and 180 ms release."""
    def __init__(self):
        self.sources = {}
        self.voices = {}
        self.volume = 0.3
        self.lock = threading.Lock()
        self.table = [math.sin(2 * math.pi * i / 2048) for i in range(2048)]

    def note(self, source, midi=None):
        with self.lock:
            if midi is None:
                self.sources.pop(source, None)
            elif 60 <= midi < 84:
                self.sources[source] = midi

    def release(self):
        with self.lock:
            self.sources.clear()

    def held(self):
        with self.lock:
            return set(self.sources.values())

    def render(self, frames):
        held = self.held()
        for note in held:
            self.voices.setdefault(note, [0.0, 0.0])
        mix = [0.0] * frames
        for note, voice in list(self.voices.items()):
            phase, envelope = voice
            step = 440 * 2 ** ((note - 69) / 12) * 2048 / RATE
            delta = 1 / (0.004 * RATE) if note in held else -1 / (0.18 * RATE)
            for i in range(frames):
                envelope = min(1.0, max(0.0, envelope + delta))
                mix[i] += self.table[int(phase) & 2047] * envelope
                phase = (phase + step) % 2048
            if envelope > 0 or note in held:
                self.voices[note] = [phase, envelope]
            else:
                del self.voices[note]
        samples = array.array("h", (int(max(-1, min(1, v * self.volume * 0.3)) * 32767)
                                    for v in mix))
        if sys.byteorder != "little":
            samples.byteswap()
        return samples.tobytes()


def smoke_test():
    synth = Synth()
    assert not any(synth.render(100))
    assert len(KEYS) == 24 and set(KEYS.values()) == set(range(60, 84))
    synth.note("a", 69)
    one = array.array("h", synth.render(RATE // 10))
    crossings = sum(a <= 0 < b for a, b in zip(one, one[1:]))
    assert 42 <= crossings <= 45, crossings
    synth.note("b", 72)
    synth.note("c", 76)
    assert any(synth.render(480)) and len(synth.voices) == 3
    synth.note("same", 69)
    synth.note("a")
    assert 69 in synth.held()
    synth.release()
    synth.render(RATE // 4)
    assert not synth.voices and not any(synth.render(480))
    print("piano smoke: PASS (24 notes, pitch, polyphony, source ownership, release)")


def audio_smoke_test():
    """Exercise PCM transport and 48 kHz stereo negotiation without sound."""
    import gi
    gi.require_version("Gst", "1.0")
    from gi.repository import Gst
    Gst.init(None)
    pipeline = Gst.parse_launch(AUDIO_PIPELINE.replace("autoaudiosink", "audio/x-raw,format=S16LE,rate=48000,channels=2 ! fakesink name=output signal-handoffs=true sync=false"))
    received = []
    pipeline.get_by_name("output").connect("handoff", lambda _sink, buffer, _pad: received.append(buffer.get_size()))
    synth = Synth()
    synth.note("a", 60)
    synth.note("b", 64)
    synth.note("c", 67)
    try:
        assert pipeline.set_state(Gst.State.PLAYING) != Gst.StateChangeReturn.FAILURE
        source = pipeline.get_by_name("synth")
        for index in range(20):
            data = synth.render(240)
            buffer = Gst.Buffer.new_allocate(None, len(data), None)
            buffer.fill(0, data)
            buffer.pts = index * Gst.SECOND // 100
            buffer.duration = Gst.SECOND // 100
            assert source.emit("push-buffer", buffer) == Gst.FlowReturn.OK
        source.emit("end-of-stream")
        message = pipeline.get_bus().timed_pop_filtered(5 * Gst.SECOND, Gst.MessageType.ERROR | Gst.MessageType.EOS)
        if message is None or message.type != Gst.MessageType.EOS:
            raise RuntimeError(message.parse_error()[0].message if message else "Audio pipeline timed out")
        assert sum(received) > 30000, received
    finally:
        pipeline.set_state(Gst.State.NULL)
    print("piano audio smoke: PASS (real Gst PCM pipeline, 48 kHz stereo, silent fakesink)")


def run_gui(ui_smoke=False):
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    gi.require_version("Gst", "1.0")
    from gi.repository import Gdk, GLib, Gst, Gtk
    GLib.set_prgname("typix-piano")
    GLib.set_application_name("Typix Piano")
    Gst.init(None)

    class Piano(Gtk.Window):
        def __init__(self):
            super().__init__(title="Piano")
            self.set_default_size(800, 500)
            self.synth, self.pipeline, self.samples = Synth(), None, 0
            self.pointer_down = False
            self.rects = []
            self.failed = False
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            box.set_border_width(16)
            self.add(box)
            title = Gtk.Label(label="Piano · two octaves")
            title.set_xalign(0)
            box.pack_start(title, False, False, 0)
            row = Gtk.Box(spacing=10)
            box.pack_start(row, False, False, 0)
            row.pack_start(Gtk.Label(label="Volume"), False, False, 0)
            volume = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 0.8, 0.01)
            volume.set_value(self.synth.volume)
            volume.set_draw_value(False)
            volume.connect("value-changed", lambda control: setattr(self.synth, "volume", control.get_value()))
            row.pack_start(volume, True, True, 0)
            release = Gtk.Button(label="Release all")
            release.connect("clicked", self.release)
            row.pack_start(release, False, False, 0)
            retry = Gtk.Button(label="Retry audio")
            retry.connect("clicked", self.retry)
            row.pack_start(retry, False, False, 0)
            self.area = Gtk.DrawingArea()
            self.area.set_size_request(400, 230)
            self.area.set_can_focus(True)
            self.area.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK |
                                 Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.TOUCH_MASK)
            self.area.connect("draw", self.draw)
            self.area.connect("button-press-event", self.pointer)
            self.area.connect("button-release-event", self.pointer)
            self.area.connect("motion-notify-event", self.pointer)
            self.area.connect("touch-event", self.touch)
            box.pack_start(self.area, True, True, 0)
            self.status = Gtk.Label(label="Touch keys or play Z–M / Q–U. Esc closes. Audio starts on first note.")
            self.status.set_line_wrap(True)
            self.status.set_xalign(0)
            box.pack_start(self.status, False, False, 0)
            self.connect("key-press-event", self.key)
            self.connect("key-release-event", self.key)
            self.connect("focus-out-event", self.release)
            self.connect("destroy", self.close)
            self.show_all()
            self.area.grab_focus()

        def retry(self, *_):
            self.stop_audio()
            self.failed = False
            self.start_audio()

        def start_audio(self):
            if self.pipeline or self.failed or ui_smoke:
                return
            try:
                self.pipeline = Gst.parse_launch(AUDIO_PIPELINE)
                self.samples = 0
                self.pipeline.get_by_name("synth").connect("need-data", self.feed)
                bus = self.pipeline.get_bus()
                bus.add_signal_watch()
                bus.connect("message::error", self.audio_error)
                if self.pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
                    raise RuntimeError("System audio could not start")
                self.status.set_text("Ready · keyboard and touch can hold notes together.")
            except Exception as error:
                self.failed = True
                self.stop_audio()
                self.status.set_text(f"Audio unavailable: {error}. Check system sound, then Retry audio.")

        def feed(self, source, _length):
            frames = 240
            data = self.synth.render(frames)
            buffer = Gst.Buffer.new_allocate(None, len(data), None)
            buffer.fill(0, data)
            buffer.pts = self.samples * Gst.SECOND // RATE
            buffer.duration = frames * Gst.SECOND // RATE
            self.samples += frames
            source.emit("push-buffer", buffer)

        def audio_error(self, _bus, message):
            error, _debug = message.parse_error()
            self.failed = True
            self.stop_audio()
            self.status.set_text(f"Audio unavailable: {error.message}. Use Retry audio after checking sound.")

        def stop_audio(self):
            self.synth.release()
            if self.pipeline:
                self.pipeline.set_state(Gst.State.NULL)
                self.pipeline.get_bus().remove_signal_watch()
                self.pipeline = None

        def release(self, *_):
            self.pointer_down = False
            self.synth.release()
            self.area.queue_draw()
            return False

        def close(self, *_):
            self.stop_audio()
            Gtk.main_quit()

        def play(self, source, note=None):
            if note is not None:
                self.start_audio()
            self.synth.note(source, note)
            self.area.queue_draw()

        def key(self, _widget, event):
            down = event.type == Gdk.EventType.KEY_PRESS
            if event.keyval == Gdk.KEY_Escape and down:
                self.destroy()
                return True
            char = chr(Gdk.keyval_to_unicode(event.keyval) or 0).lower()
            if char in KEYS:
                self.play(("key", event.hardware_keycode), KEYS[char] if down else None)
                return True
            # A layout/shift change must still release the original physical key.
            if not down:
                self.play(("key", event.hardware_keycode))
            return False

        def hit(self, x, y):
            for midi, left, top, width, height, _black in reversed(self.rects):
                if left <= x < left + width and top <= y < top + height:
                    return midi
            return None

        def pointer(self, _widget, event):
            if event.get_pointer_emulated():
                return True
            if event.type == Gdk.EventType.BUTTON_PRESS:
                if event.button != 1:
                    return False
                self.pointer_down = True
                self.area.grab_focus()
            elif event.type == Gdk.EventType.BUTTON_RELEASE:
                self.pointer_down = False
            self.play("pointer", self.hit(event.x, event.y) if self.pointer_down else None)
            return True

        def touch(self, _widget, event):
            source = ("touch", event.get_event_sequence())
            end = event.type in (Gdk.EventType.TOUCH_END, Gdk.EventType.TOUCH_CANCEL)
            self.play(source, None if end else self.hit(event.x, event.y))
            return True

        def draw(self, widget, context):
            width, height = widget.get_allocated_width(), widget.get_allocated_height()
            step = width / 14
            self.rects = [(note, i * step, 0, step, height, False) for i, note in enumerate(WHITE)]
            self.rects += [(note, (after + 1) * step - step * .32, 0, step * .64, height * .61, True)
                           for note, after in BLACK]
            held = self.synth.held()
            names = {value: key.upper() for key, value in KEYS.items()}
            for note, x, y, w, h, black in self.rects:
                color = (.28, .52, .91) if note in held else ((.12, .14, .18) if black else (.96, .97, .98))
                context.set_source_rgb(*color)
                context.rectangle(x + 1, y, w - 2, h - 1)
                context.fill()
                context.set_source_rgb(*((.95, .95, .97) if black else (.15, .18, .23)))
                context.set_font_size(13)
                context.move_to(x + w / 2 - 5, h - 22)
                context.show_text(names[note])

    window = Piano()
    if not ui_smoke and os.environ.get("TYPIX_WINDOWED") != "1":
        window.fullscreen()
    if ui_smoke:
        if os.environ.get("C1MAX_UI_SCREENSHOT"):
            def screenshot():
                Gdk.pixbuf_get_from_window(window.get_window(), 0, 0, window.get_allocated_width(),
                                          window.get_allocated_height()).savev(os.environ["C1MAX_UI_SCREENSHOT"], "png", [], [])
                return False
            GLib.timeout_add(650, screenshot)
        GLib.timeout_add(400, lambda: (window.play("test", 60), False)[1])
        GLib.timeout_add(1000, lambda: (window.destroy(), False)[1])
    Gtk.main()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--ui-smoke-test", action="store_true")
    parser.add_argument("--audio-smoke-test", action="store_true")
    args = parser.parse_args(argv)
    if args.smoke_test:
        smoke_test()
        return 0
    try:
        if args.audio_smoke_test:
            audio_smoke_test()
        else:
            run_gui(args.ui_smoke_test)
    except (ImportError, ValueError, RuntimeError) as error:
        print(f"Piano: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

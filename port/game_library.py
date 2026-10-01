#!/usr/bin/env python3
"""Native library and session control for distribution DOSBox/Mednafen.

The emulators are audited Debian Depends, not downloads or bundled game images.
Imports retain user-selected paths and never delete games, BIOS, or save data.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def data_dir(kind):
    root = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share'))
    return root / ('typix-' + kind)


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temp = tempfile.mkstemp(prefix='.library-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def import_bios(source, destination):
    """Publish a complete private BIOS atomically; preserve existing firmware."""
    if source.name.lower() not in {'scph5500.bin', 'scph5501.bin', 'scph5502.bin'} or source.stat().st_size != 512 * 1024:
        raise ValueError('Select a 512 KiB scph5500.bin, scph5501.bin, or scph5502.bin BIOS.')
    fd, temporary = tempfile.mkstemp(prefix='.bios-', dir=destination.parent)
    temporary = Path(temporary)
    try:
        with os.fdopen(fd, 'wb') as output, source.open('rb') as original:
            shutil.copyfileobj(original, output)
            output.flush()
            if output.tell() != 512 * 1024:
                raise ValueError('BIOS changed during import; no firmware was published.')
            os.fsync(output.fileno())
        # Same-directory hardlink is atomic and refuses any existing destination.
        # os.replace would overwrite firmware selected in another window.
        os.link(temporary, destination)
        directory = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def command(kind, item, root):
    path = Path(item['path']).expanduser().resolve(strict=True)
    if kind == 'dosbox':
        if not path.is_dir():
            raise ValueError('DOS games need a complete directory, including their data files.')
        # DOSBox parses its own commands. Refuse command delimiters in paths.
        if any(c in str(path) for c in ('"', '\r', '\n')):
            raise ValueError('Choose a directory path without quotes or line breaks.')
        return ['dosbox', '-conf', str(root / 'dosbox.conf'), '-c', f'mount c "{path}"', '-c', 'c:']
    if path.suffix.lower() not in {'.cue', '.m3u', '.chd', '.toc', '.ccd'}:
        raise ValueError('Select a CUE, CCD, TOC, CHD or M3U disc definition; keep its track files together.')
    return ['mednafen', '-video.fs', '1', '-filesys.path_firmware', str(root / 'firmware'), str(path)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--kind', choices=('dosbox', 'ps1'), default=('ps1' if Path(__file__).parent.name.endswith('ps1') else 'dosbox'))
    parser.add_argument('--smoke-test', action='store_true')
    parser.add_argument('--ui-smoke-test', action='store_true')
    args = parser.parse_args()
    if args.smoke_test:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            assert command('dosbox', {'path': temp}, root)[-1] == 'c:'
            disc = root / 'example.cue'
            disc.write_text('FILE "example.bin" BINARY\n')
            assert command('ps1', {'path': str(disc)}, root)[0] == 'mednafen'
            atomic_json(root / 'library.json', [{'path': temp}])
            assert json.loads((root / 'library.json').read_text())[0]['path'] == temp
        print('game library checks passed')
        return 0
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk, Gdk, GLib
    kind = args.kind
    GLib.set_prgname("typix-" + kind)
    GLib.set_application_name("Typix " + ("DOSBox" if kind == "dosbox" else "PS1"))
    root = data_dir(kind)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    (root / 'firmware').mkdir(exist_ok=True, mode=0o700)
    if kind == 'dosbox' and not (root / 'dosbox.conf').exists():
        (root / 'dosbox.conf').write_text('[sdl]\nfullscreen=true\nfulldouble=false\noutput=surface\n\n[cpu]\ncore=normal\ncycles=auto\n\n[mixer]\nrate=44100\n')
    library_path = root / 'library.json'
    load_error = ''
    try:
        items = json.loads(library_path.read_text())
        if not isinstance(items, list) or not all(isinstance(x, dict) and isinstance(x.get('path'), str) for x in items):
            raise ValueError('Invalid library data')
    except FileNotFoundError:
        items = []
    except (OSError, ValueError) as error:
        items = []
        load_error = f'Library cannot be read: {error}. Existing file was preserved.'
    title = 'Typix DOSBox' if kind == 'dosbox' else 'Typix PS1'
    window = Gtk.Window(title=title)
    window.set_default_size(800, 600)
    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin=16)
    window.add(outer)
    header = Gtk.Label(label=title, xalign=0)
    header.set_markup(f'<span size="xx-large" weight="bold">{title}</span>')
    outer.pack_start(header, False, False, 0)
    help_text = ('Import a DOS game directory. The DOS prompt opens on C:. Type its EXE/COM name.\nCtrl+F9 closes the emulator; game saves remain in the selected directory.' if kind == 'dosbox' else
                 'Import your own PS1 disc definition and keep all track files alongside it.\nMednafen: F5 save state · F7 load · Alt+Shift+1 configure controls · Esc exits.\nProvide your legally obtained BIOS with Import BIOS; no games or BIOS are included.')
    help_label = Gtk.Label(label=help_text, xalign=0, wrap=True)
    outer.pack_start(help_label, False, False, 0)
    status = Gtk.Label(label=load_error or 'Choose a game, then Play.', xalign=0, wrap=True)
    model = Gtk.ListStore(str, str)
    tree = Gtk.TreeView(model=model)
    tree.append_column(Gtk.TreeViewColumn('Game', Gtk.CellRendererText(), text=0))
    tree.append_column(Gtk.TreeViewColumn('User-selected location', Gtk.CellRendererText(), text=1))
    scroll = Gtk.ScrolledWindow()
    scroll.add(tree)
    outer.pack_start(scroll, True, True, 0)
    bar = Gtk.Box(spacing=8)
    outer.pack_start(bar, False, False, 0)
    # Library actions belong beside the title, rather than a fixed bottom strip.
    outer.reorder_child(bar, 1)
    outer.pack_start(status, False, False, 0)
    process = [None]
    def refresh():
        model.clear()
        for item in items:
            p = Path(item['path'])
            model.append([p.stem + ('' if p.exists() else ' (missing)'), str(p)])
    def save():
        if load_error:
            raise ValueError('Repair or back up the unreadable library before importing. It has not been overwritten.')
        atomic_json(library_path, items)
    def choose(bios=False):
        action = Gtk.FileChooserAction.SELECT_FOLDER if kind == 'dosbox' and not bios else Gtk.FileChooserAction.OPEN
        dialog = Gtk.FileChooserDialog(title='Import BIOS' if bios else 'Import game', transient_for=window, action=action)
        dialog.add_buttons('Cancel', Gtk.ResponseType.CANCEL, 'Import', Gtk.ResponseType.OK)
        try:
            if dialog.run() != Gtk.ResponseType.OK:
                return
            path = Path(dialog.get_filename()).resolve(strict=True)
            if bios:
                dest = root / 'firmware' / path.name.lower()
                if dest.exists():
                    raise ValueError('That BIOS already exists; existing data was preserved.')
                import_bios(path, dest)
                status.set_text('BIOS copied to your private PS1 data directory.')
            else:
                item = {'path': str(path)}
                command(kind, item, root)
                if item not in items:
                    items.append(item)
                    try:
                        save()
                    except Exception:
                        items.pop()
                        raise
                refresh()
                status.set_text('Game location added. Original files were preserved.')
        except (OSError, ValueError) as error:
            status.set_text(str(error))
        finally:
            dialog.destroy()
    def play(*unused):
        if process[0] is not None:
            status.set_text('A game is already running. Return to it with Alt+Tab.')
            return
        selection, iterator = tree.get_selection().get_selected()
        if iterator is None:
            status.set_text('Select a game first.')
            return
        try:
            argv = command(kind, {'path': model[iterator][1]}, root)
            if not shutil.which(argv[0]):
                raise ValueError(f'{argv[0]} is unavailable. Reinstall this deb with its declared Debian dependencies.')
            log = (root / 'session.log').open('w')
            try:
                process[0] = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT, cwd=root, env=dict(os.environ, MEDNAFEN_HOME=str(root)), start_new_session=True)
            finally:
                log.close()
            status.set_text('Game running. Alt+Tab returns here; save before closing the emulator.')
        except (OSError, ValueError) as error:
            status.set_text(str(error))
    def forget(button):
        _, iterator = tree.get_selection().get_selected()
        if iterator is None:
            return
        index = model.get_path(iterator).get_indices()[0]
        old = items.pop(index)
        try:
            save()
        except (OSError, ValueError) as error:
            items.insert(index, old)
            status.set_text(str(error))
        refresh()
    for label, callback in [('Import game', lambda b: choose()), ('Play', play), ('Remove from list', forget)]:
        button = Gtk.Button(label=label)
        button.connect('clicked', callback)
        bar.pack_start(button, False, False, 0)
    if kind == 'ps1':
        button = Gtk.Button(label='Import BIOS')
        button.connect('clicked', lambda b: choose(True))
        bar.pack_start(button, False, False, 0)
    def poll():
        if process[0] is not None and process[0].poll() is not None:
            code = process[0].returncode
            process[0] = None
            status.set_text('Game closed.' if code == 0 else f'Emulator exited ({code}). Check {root / "session.log"}; BIOS/game compatibility may be required.')
        return True
    def closing(*unused):
        if process[0] is not None:
            status.set_text('Close the game first so its save files can finish writing.')
            return True
        Gtk.main_quit()
        return False
    window.connect('delete-event', closing)
    tree.connect('row-activated', play)
    window.connect('key-press-event', lambda w, e: closing() if e.keyval == Gdk.KEY_Escape else False)
    GLib.timeout_add(500, poll)
    refresh()
    window.show_all()
    if not args.ui_smoke_test and os.environ.get('TYPIX_WINDOWED') != '1':
        window.fullscreen()
    if args.ui_smoke_test:
        if os.environ.get('C1MAX_UI_SCREENSHOT'):
            def screenshot():
                Gdk.pixbuf_get_from_window(window.get_window(), 0, 0, window.get_allocated_width(), window.get_allocated_height()).savev(os.environ['C1MAX_UI_SCREENSHOT'], 'png', [], [])
                return False
            GLib.timeout_add(650, screenshot)
        GLib.timeout_add(1100, Gtk.main_quit)
    Gtk.main()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

#!/usr/bin/env python3
"""A small, user-local wallpaper picker for Cinnamon."""
import hashlib
import json
import os
import random
from collections import OrderedDict
from pathlib import Path

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk

APP = "cinnamon-wallpaper-carousel"
CONFIG = Path.home() / ".config" / APP
CACHE = Path.home() / ".cache" / APP
THUMBS = CACHE / "thumbnails"
EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
DEFAULTS = {"folders": [str(Path.home() / "Pictures" / "Wallpapers")], "thumbnail_size": 160,
            "animation": True, "close_after_apply": False, "apply_on_double_click": True,
            "remember_position": True, "performance": "Balanced", "last_path": ""}

CSS = b"""
window { background: #161a22; color: #e9edf4; }
headerbar { background: #202634; border-bottom: 1px solid #30394b; }
.muted { color: #aeb8c8; } .title { font-size: 18px; font-weight: bold; }
button { background: #293142; color: #e9edf4; border: 0; border-radius: 8px; padding: 7px 11px; }
button:hover { background: #39455d; } button.suggested-action { background: #6d7cce; }
entry, combobox button { background: #222a38; color: #e9edf4; border-color: #3b465d; }
.card { background: #202634; border-radius: 14px; padding: 10px; }
.image-frame { background: #0e1118; border-radius: 10px; }
"""

def read_json(name, default):
    try:
        with open(CONFIG / name, encoding="utf-8") as f: return json.load(f)
    except (OSError, ValueError): return default

def write_json(name, value):
    CONFIG.mkdir(parents=True, exist_ok=True)
    temp = CONFIG / (name + ".tmp")
    with open(temp, "w", encoding="utf-8") as f: json.dump(value, f, ensure_ascii=False, indent=2)
    os.replace(temp, CONFIG / name)

def fit_pixbuf(path, width, height):
    pix = GdkPixbuf.Pixbuf.new_from_file(path)
    scale = min(width / pix.get_width(), height / pix.get_height(), 1.0)
    return pix.scale_simple(max(1, int(pix.get_width()*scale)), max(1, int(pix.get_height()*scale)), GdkPixbuf.InterpType.BILINEAR)

class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="io.github.cinnamonwallpapercarousel", flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.settings = {**DEFAULTS, **read_json("settings.json", {})}
        self.favorites = set(read_json("favorites.json", []))
        self.history = read_json("history.json", [])
        self.all_files, self.files, self.index, self.slide_direction = [], [], 0, 0
        self.full_cache = OrderedDict(); self.thumb_cache = OrderedDict()
        self.scan_queue = []; self.scan_id = 0

    def do_activate(self):
        if getattr(self, "win", None): self.win.present(); return
        provider = Gtk.CssProvider(); provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.build_ui(); self.start_scan()

    def build_ui(self):
        self.win = Gtk.ApplicationWindow(application=self, title="Wallpapers")
        self.win.set_default_size(900, 620); self.win.set_size_request(620, 480)
        self.win.connect("key-press-event", self.key)
        header = Gtk.HeaderBar(title="Wallpapers", show_close_button=True)
        self.win.set_titlebar(header)
        gear = Gtk.Button.new_from_icon_name("emblem-system-symbolic", Gtk.IconSize.BUTTON); gear.set_tooltip_text("Settings")
        gear.connect("clicked", lambda *_: self.show_settings()); header.pack_end(gear)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin=16)
        self.win.add(root)
        controls = Gtk.Box(spacing=8); root.pack_start(controls, False, False, 0)
        self.search = Gtk.SearchEntry(placeholder_text="Search filenames…"); self.search.connect("search-changed", lambda *_: self.filter()); controls.pack_start(self.search, True, True, 0)
        self.filter_combo = Gtk.ComboBoxText(); [self.filter_combo.append_text(x) for x in ("All", "Favorites", "Recently Used")]
        self.filter_combo.set_active(0); self.filter_combo.connect("changed", lambda *_: self.filter()); controls.pack_start(self.filter_combo, False, False, 0)
        self.count = Gtk.Label(label="Scanning…"); self.count.get_style_context().add_class("muted"); controls.pack_end(self.count, False, False, 0)
        carousel = Gtk.Box(spacing=10); root.pack_start(carousel, True, True, 0)
        left = Gtk.Button.new_from_icon_name("go-previous-symbolic", Gtk.IconSize.DIALOG); left.connect("clicked", lambda *_: self.move(-1)); carousel.pack_start(left, False, False, 0)
        self.prev = self.make_side(); carousel.pack_start(self.prev, True, True, 0)
        # Gtk.Stack gives us a cheap compositor-driven slide without a timer or
        # a per-frame redraw loop. Only two image widgets ever exist here.
        self.center = Gtk.EventBox(); self.center.connect("button-press-event", self.center_click)
        self.stage = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_LEFT, transition_duration=200)
        self.images = []
        for slot in ("one", "two"):
            frame = Gtk.Frame(); frame.get_style_context().add_class("image-frame")
            image = Gtk.Image(); frame.add(image); self.stage.add_named(frame, slot); self.images.append(image)
        self.stage.set_visible_child_name("one"); self.image_slot = 0; self.image = self.images[0]
        self.center.add(self.stage); carousel.pack_start(self.center, True, True, 0)
        self.next = self.make_side(); carousel.pack_start(self.next, True, True, 0)
        right = Gtk.Button.new_from_icon_name("go-next-symbolic", Gtk.IconSize.DIALOG); right.connect("clicked", lambda *_: self.move(1)); carousel.pack_start(right, False, False, 0)
        self.center.connect("scroll-event", self.scroll)
        self.name = Gtk.Label(ellipsize=3); self.name.get_style_context().add_class("muted"); root.pack_start(self.name, False, False, 0)
        self.thumbbox = Gtk.Box(spacing=7); viewport = Gtk.ScrolledWindow(); viewport.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER); viewport.set_min_content_height(120); viewport.add(self.thumbbox); root.pack_start(viewport, False, True, 0)
        bottom = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER); root.pack_start(bottom, False, False, 0)
        self.favorite = Gtk.Button(label="☆ Favorite"); self.favorite.connect("clicked", lambda *_: self.toggle_favorite()); bottom.pack_start(self.favorite, False, False, 0)
        apply = Gtk.Button(label="Set Wallpaper"); apply.get_style_context().add_class("suggested-action"); apply.connect("clicked", lambda *_: self.apply()); bottom.pack_start(apply, False, False, 0)
        self.win.show_all()

    def make_side(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER, spacing=5)
        img = Gtk.Image(); img.set_size_request(140, 105); box.pack_start(img, False, False, 0); label = Gtk.Label(ellipsize=3, max_width_chars=17); label.get_style_context().add_class("muted"); box.pack_start(label, False, False, 0)
        box.preview_image, box.preview_label = img, label; return box

    def start_scan(self):
        self.all_files = []; self.scan_queue = [Path(x).expanduser() for x in self.settings["folders"] if Path(x).expanduser().is_dir()]
        if self.scan_id: GLib.source_remove(self.scan_id)
        self.scan_id = GLib.idle_add(self.scan_step)

    def scan_step(self):
        if not self.scan_queue:
            self.scan_id = 0; self.filter(); return False
        folder = self.scan_queue.pop(0)
        try:
            for root, dirs, names in os.walk(str(folder)):
                # Skip hidden trees; this keeps accidental huge scans at bay.
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                self.all_files.extend(str(Path(root, n)) for n in names if Path(n).suffix.lower() in EXTENSIONS)
        except OSError: pass
        return True

    def filter(self):
        old = self.current_path()
        text = self.search.get_text().casefold(); mode = self.filter_combo.get_active_text()
        source = self.all_files
        if mode == "Favorites": source = [x for x in source if x in self.favorites]
        elif mode == "Recently Used": source = [x for x in self.history if x in self.all_files]
        self.files = [x for x in source if text in Path(x).name.casefold() and Path(x).is_file()]
        self.index = self.files.index(old) if old in self.files else 0
        if self.settings["remember_position"] and self.settings["last_path"] in self.files: self.index = self.files.index(self.settings["last_path"])
        self.refresh()

    def current_path(self): return self.files[self.index] if self.files else None
    def move(self, delta):
        if self.files:
            self.slide_direction = delta
            self.index = (self.index + delta) % len(self.files); self.refresh()
    def scroll(self, _w, event): self.move(1 if event.direction in (Gdk.ScrollDirection.DOWN, Gdk.ScrollDirection.RIGHT) else -1); return True

    def cached(self, path, size, thumbnail=False):
        cache = self.thumb_cache if thumbnail else self.full_cache; key = (path, size)
        if key in cache: cache.move_to_end(key); return cache[key]
        try:
            if thumbnail:
                stamp = os.stat(path); digest = hashlib.sha256((path+str(stamp.st_mtime_ns)+str(stamp.st_size)).encode()).hexdigest(); disk = THUMBS / (digest+".png")
                if disk.exists(): pix = GdkPixbuf.Pixbuf.new_from_file(str(disk))
                else:
                    THUMBS.mkdir(parents=True, exist_ok=True); pix = fit_pixbuf(path, size, size); pix.savev(str(disk), "png", [], [])
            else: pix = fit_pixbuf(path, max(240, self.image.get_allocated_width()-24), max(180, self.image.get_allocated_height()-24))
        except Exception: return None
        cache[key] = pix
        limits = {"Low": (20, 2), "Balanced": (36, 3), "High": (60, 5)}
        while len(cache) > limits.get(self.settings["performance"], (36, 3))[0 if thumbnail else 1]: cache.popitem(last=False)
        return pix

    def refresh(self):
        path = self.current_path()
        for child in self.thumbbox.get_children(): self.thumbbox.remove(child)
        if path and not Path(path).is_file():
            # A file can disappear while the picker is open; discard it rather
            # than retaining a broken carousel item.
            self.files.pop(self.index)
            if self.files: self.index %= len(self.files)
            self.refresh(); return
        if not path:
            self.image.clear(); self.name.set_text("No supported images found in configured folders"); self.count.set_text("0 / 0"); return
        self.settings["last_path"] = path; self.save_settings()
        pix = self.cached(path, 0)
        # Reusing the outgoing slot lets Gtk animate just the two nearby images.
        self.stage.set_transition_duration(200 if self.settings["animation"] else 0)
        self.stage.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT if self.slide_direction >= 0 else Gtk.StackTransitionType.SLIDE_RIGHT)
        self.image_slot = 1 - self.image_slot; self.image = self.images[self.image_slot]
        self.image.set_from_pixbuf(pix) if pix else self.image.clear()
        self.stage.set_visible_child_name(("one", "two")[self.image_slot])
        self.name.set_text(Path(path).name + ("  (could not load)" if not pix else "")); self.count.set_text(f"{self.index + 1} / {len(self.files)}")
        self.favorite.set_label("★ Favorite" if path in self.favorites else "☆ Favorite")
        for box, offset in ((self.prev, -1), (self.next, 1)):
            other = self.files[(self.index+offset) % len(self.files)] if len(self.files) > 1 else None
            p = self.cached(other, 140, True) if other else None; box.preview_image.set_from_pixbuf(p) if p else box.preview_image.clear(); box.preview_label.set_text(Path(other).name if other else "")
        start = max(0, self.index-5); end = min(len(self.files), start+11)
        for i in range(start, end):
            button = Gtk.Button(); thumb = self.cached(self.files[i], int(self.settings["thumbnail_size"]), True); button.set_image(Gtk.Image.new_from_pixbuf(thumb) if thumb else Gtk.Image()); button.set_tooltip_text(Path(self.files[i]).name); button.connect("clicked", lambda _b, n=i: self.select(n)); self.thumbbox.pack_start(button, False, False, 0)
        self.thumbbox.show_all()

    def select(self, n): self.slide_direction = 1 if n >= self.index else -1; self.index = n; self.refresh()
    def center_click(self, _w, event):
        if event.type == Gdk.EventType._2BUTTON_PRESS and self.settings["apply_on_double_click"]: self.apply()
        return True
    def toggle_favorite(self):
        p = self.current_path()
        if p in self.favorites: self.favorites.remove(p)
        elif p: self.favorites.add(p)
        write_json("favorites.json", sorted(self.favorites)); self.refresh()
    def apply(self):
        p = self.current_path()
        if not p: return
        try: Gio.Settings.new("org.cinnamon.desktop.background").set_string("picture-uri", Gio.File.new_for_path(p).get_uri())
        except Exception as exc: self.message("Could not set Cinnamon wallpaper: " + str(exc)); return
        self.history = [x for x in self.history if x != p]; self.history.insert(0, p); self.history = self.history[:50]; write_json("history.json", self.history)
        if self.settings["close_after_apply"]: self.quit()
    def key(self, _w, e):
        k = Gdk.keyval_name(e.keyval)
        if k == "Left": self.move(-1)
        elif k == "Right": self.move(1)
        elif k in ("Return", "KP_Enter"): self.apply()
        elif k == "Escape": self.quit()
        elif k in ("r", "R"): self.select(random.randrange(len(self.files))) if self.files else None
        elif k in ("f", "F"): self.toggle_favorite()
        elif k == "Home": self.select(0)
        elif k == "End" and self.files: self.select(len(self.files)-1)
        else: return False
        return True
    def save_settings(self): write_json("settings.json", self.settings)
    def message(self, text):
        d = Gtk.MessageDialog(transient_for=self.win, modal=True, message_type=Gtk.MessageType.ERROR, buttons=Gtk.ButtonsType.CLOSE, text=text); d.run(); d.destroy()

    def show_settings(self):
        d = Gtk.Dialog(title="Settings", transient_for=self.win, modal=True); d.add_button("Close", Gtk.ResponseType.CLOSE)
        box = d.get_content_area(); grid = Gtk.Grid(row_spacing=9, column_spacing=10, margin=16); box.add(grid)
        folders = Gtk.Entry(text="\n".join(self.settings["folders"])); folders.set_tooltip_text("One existing folder per line. Only these folders are scanned.")
        grid.attach(Gtk.Label(label="Folders (one per line):", halign=Gtk.Align.START), 0, 0, 1, 1); grid.attach(folders, 1, 0, 1, 1)
        spin = Gtk.SpinButton.new_with_range(80, 320, 10); spin.set_value(self.settings["thumbnail_size"]); grid.attach(Gtk.Label(label="Thumbnail size:"), 0, 1, 1, 1); grid.attach(spin, 1, 1, 1, 1)
        checks = {}
        for row, (key, label) in enumerate((("animation", "Enable animations"),("close_after_apply", "Close after applying"),("apply_on_double_click", "Apply on double-click"),("remember_position", "Remember last position")), 2):
            checks[key] = Gtk.CheckButton(label=label, active=bool(self.settings[key])); grid.attach(checks[key], 1, row, 1, 1)
        preset = Gtk.ComboBoxText(); [preset.append_text(x) for x in ("Low", "Balanced", "High")]; preset.set_active(("Low", "Balanced", "High").index(self.settings["performance"])); grid.attach(Gtk.Label(label="Performance preset:"), 0, 6, 1, 1); grid.attach(preset, 1, 6, 1, 1)
        d.show_all(); d.run()
        self.settings.update({"folders":[x.strip() for x in folders.get_text().splitlines() if x.strip()], "thumbnail_size":spin.get_value_as_int(), "performance":preset.get_active_text()})
        self.settings.update({k: checks[k].get_active() for k in checks}); self.save_settings(); d.destroy(); self.start_scan()

if __name__ == "__main__": App().run(None)

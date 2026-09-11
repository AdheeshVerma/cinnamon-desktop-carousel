# Cinnamon Wallpaper Carousel

A small GTK3/X11-friendly wallpaper chooser for Linux Mint Cinnamon. It is a normal application, not a service: it exits completely when its window closes. It scans only folders listed in Settings, creates thumbnails on demand, keeps at most three display-sized images in memory, and changes only `org.cinnamon.desktop.background picture-uri` through GSettings.

## Requirements

Linux Mint normally provides `python3-gi` and `gir1.2-gtk-3.0` already for
Cinnamon applications. There are no pip dependencies and the application (and
its user-local installer) never needs sudo. WEBP decoding depends on the
system GdkPixbuf loader.

## Run from this folder

```sh
python3 wallpaper_carousel.py
```

The default folder is `~/Pictures/Wallpapers`. Add folders in the gear menu; no other locations are scanned. Supported files are JPG/JPEG, PNG, WEBP, and BMP.

## Optional user-local installation

```sh
chmod +x install-user.sh
./install-user.sh
```

The installer creates or changes only:

- `~/.local/share/cinnamon-wallpaper-carousel/wallpaper_carousel.py` — application copy.
- `~/.local/bin/wallpaper-carousel` — small launcher.
- `~/.local/share/applications/cinnamon-wallpaper-carousel.desktop` — menu entry.

At first use the app may create `~/.config/cinnamon-wallpaper-carousel/{settings,favorites,history}.json` and cached thumbnail PNGs under `~/.cache/cinnamon-wallpaper-carousel/thumbnails/`. It creates no autostart entry, daemon, or system files.

## Uninstall

```sh
rm -f ~/.local/bin/wallpaper-carousel ~/.local/share/applications/cinnamon-wallpaper-carousel.desktop
rm -rf ~/.local/share/cinnamon-wallpaper-carousel ~/.config/cinnamon-wallpaper-carousel ~/.cache/cinnamon-wallpaper-carousel
```

This removes only this app's code, launcher, settings, history, favorites, and thumbnail cache. It never removes or changes source wallpapers.

## Controls

`Left`/`Right` navigate, `Enter` applies, `Esc` closes, `R` chooses a random preview, `F` favorites, and `Home`/`End` jump. **Random + Apply** selects a random wallpaper from the current search/filter results and immediately makes it the Cinnamon desktop background. Mouse arrows, thumbnails, mouse wheel, and a double-click on the main image work as expected. Search filters names; filters cover All, Favorites, recently applied wallpapers, and broad dominant-color families (including light, dark, and neutral).

## Bind a key to launch it

Use Cinnamon's per-user desktop shortcut: **System Settings → Keyboard → Shortcuts → Custom Shortcuts → Add custom shortcut**. After running the optional installer, use this command:

```sh
~/.local/bin/wallpaper-carousel
```

Assign a key combination there. This is deliberately a Cinnamon setting rather than app code: it is global, persists independently of source changes, and launches the picker from any application.

Performance presets cap the in-memory thumbnail/display-image caches (Low: 20/2, Balanced: 36/3, High: 60/5). The app avoids visual effects; its optional 200ms slide uses GTK3's stack transition rather than a timer-driven animation engine.

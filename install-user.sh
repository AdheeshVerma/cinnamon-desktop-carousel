#!/usr/bin/env sh
# Installs only under the current user's ~/.local; no root access is used.
set -eu
src=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
dest="$HOME/.local/share/cinnamon-wallpaper-carousel"
mkdir -p "$dest" "$HOME/.local/bin" "$HOME/.local/share/applications"
install -m 755 "$src/wallpaper_carousel.py" "$dest/wallpaper_carousel.py"
printf '%s\n' '#!/usr/bin/env sh' 'exec python3 "$HOME/.local/share/cinnamon-wallpaper-carousel/wallpaper_carousel.py" "$@"' > "$HOME/.local/bin/wallpaper-carousel"
chmod 755 "$HOME/.local/bin/wallpaper-carousel"
install -m 644 "$src/cinnamon-wallpaper-carousel.desktop" "$HOME/.local/share/applications/cinnamon-wallpaper-carousel.desktop"
echo "Installed. Ensure ~/.local/bin is on PATH, then launch Wallpaper Carousel."

#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 1 ]; then
    echo "Usage: $0 <version> [app_dir] [out_dir]" >&2
    exit 1
fi

VERSION_RAW="$1"
APP_DIR="${2:-dist/Datamosh}"
OUT_DIR="${3:-release-artifacts}"
VERSION="${VERSION_RAW#v}"

if [ ! -d "$APP_DIR" ]; then
    echo "App directory not found: $APP_DIR" >&2
    exit 1
fi

ARCH="$(uname -m)"
case "$ARCH" in
    x86_64|aarch64)
        APPIMAGE_ARCH="$ARCH"
        ;;
    *)
        echo "Unsupported architecture for AppImage: $ARCH" >&2
        exit 1
        ;;
esac

WORK_DIR="$(mktemp -d)"
TOOL_PATH="$WORK_DIR/appimagetool.AppImage"
APPDIR="$WORK_DIR/Datamosh.AppDir"
trap 'rm -rf "$WORK_DIR"' EXIT

mkdir -p "$OUT_DIR" "$APPDIR/usr/bin" "$APPDIR/usr/lib/datamosh"

cp -a "$APP_DIR/." "$APPDIR/usr/lib/datamosh/"
cp -a assets/showcase/ui-preview.png "$APPDIR/datamosh.png"
ln -sf datamosh.png "$APPDIR/.DirIcon"

cat > "$APPDIR/usr/bin/datamosh-gui" <<'EOF'
#!/usr/bin/env bash
HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
exec "$HERE/../lib/datamosh/Datamosh" "$@"
EOF
chmod 0755 "$APPDIR/usr/bin/datamosh-gui"

cat > "$APPDIR/AppRun" <<'EOF'
#!/usr/bin/env bash
HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
exec "$HERE/usr/bin/datamosh-gui" "$@"
EOF
chmod 0755 "$APPDIR/AppRun"

cat > "$APPDIR/datamosh.desktop" <<'EOF'
[Desktop Entry]
Name=Datamosh
Comment=Timeline-based datamoshing editor
Exec=datamosh-gui
Terminal=false
Type=Application
Icon=datamosh
Categories=AudioVideo;Video;
EOF

curl -fsSL -o "$TOOL_PATH" \
    "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-${APPIMAGE_ARCH}.AppImage"
chmod 0755 "$TOOL_PATH"

APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL_PATH" "$APPDIR" \
    "$OUT_DIR/Datamosh-${VERSION}-linux-${APPIMAGE_ARCH}.AppImage"

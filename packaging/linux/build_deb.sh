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

ARCH="$(dpkg --print-architecture)"
WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

PKG_ROOT="$WORK_DIR/datamosh-gui"
mkdir -p \
    "$PKG_ROOT/DEBIAN" \
    "$PKG_ROOT/opt/datamosh" \
    "$PKG_ROOT/usr/bin" \
    "$PKG_ROOT/usr/share/applications"

cp -a "$APP_DIR/." "$PKG_ROOT/opt/datamosh/"

cat > "$PKG_ROOT/usr/bin/datamosh" <<'EOF'
#!/usr/bin/env bash
exec /opt/datamosh/Datamosh "$@"
EOF
chmod 0755 "$PKG_ROOT/usr/bin/datamosh"

cat > "$PKG_ROOT/usr/share/applications/datamosh.desktop" <<'EOF'
[Desktop Entry]
Name=Datamosh
Comment=Timeline-based datamoshing editor
Exec=datamosh
Terminal=false
Type=Application
Categories=AudioVideo;Video;
EOF

cat > "$PKG_ROOT/DEBIAN/control" <<EOF
Package: datamosh-gui
Version: $VERSION
Section: video
Priority: optional
Architecture: $ARCH
Maintainer: Datamosh GUI
Depends: ffmpeg
Description: Datamosh GUI
 Timeline-based datamoshing editor with clip and timeline controls.
EOF

mkdir -p "$OUT_DIR"
dpkg-deb --build "$PKG_ROOT" "$OUT_DIR/Datamosh-${VERSION}-linux-installer.deb"

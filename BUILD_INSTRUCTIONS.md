# Build Instructions for All Platforms

This document provides instructions for building portable executables for Linux, Windows, and macOS.

## Prerequisites

- Python 3.10+ installed
- All dependencies from `requirements.txt`
- PyInstaller: `pip install pyinstaller`

---

## Linux (AppImage)

### Quick Build

```bash
# Install dependencies
pip install -r requirements.txt
pip install pyinstaller

# Build the executable
pyinstaller --clean datamosh-gui.spec

# Download appimagetool
cd AppImage
wget https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage
chmod +x appimagetool-x86_64.AppImage

# Build AppImage
ARCH=x86_64 ./appimagetool-x86_64.AppImage Datamosh-GUI.AppDir Datamosh-GUI-x86_64.AppImage
```

### Result
- **File**: `Datamosh-GUI-x86_64.AppImage` (~103 MB)
- **Usage**: `chmod +x Datamosh-GUI-x86_64.AppImage && ./Datamosh-GUI-x86_64.AppImage`
- **Compatible**: Most Linux distributions (Ubuntu, Fedora, Arch, etc.)

---

## Windows (Standalone EXE)

### Prerequisites (on Windows)
- Python 3.10+ from python.org
- Visual C++ Redistributable (usually included)

### Build Steps

```powershell
# Install dependencies
pip install -r requirements.txt
pip install pyinstaller

# Build standalone EXE
pyinstaller --onefile --windowed --name "Datamosh-GUI" `
    --icon=datamosh-gui.ico `
    --add-data "README.md;." `
    --add-data "LICENSE;." `
    --hidden-import=PIL._tkinter_finder `
    --hidden-import=tkinterdnd2 `
    --hidden-import=cv2 `
    mosh_gui.py

# Or use the spec file
pyinstaller --clean datamosh-gui-windows.spec
```

### Windows Spec File (datamosh-gui-windows.spec)

```python
# -*- mode: python ; coding: utf-8 -*-
block_cipher = None

a = Analysis(
    ['mosh_gui.py'],
    pathex=[],
    binaries=[],
    datas=[('README.md', '.'), ('LICENSE', '.')],
    hiddenimports=['PIL._tkinter_finder', 'tkinterdnd2', 'cv2'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'numpy.testing', 'scipy', 'pandas'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Datamosh-GUI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='datamosh-gui.ico'  # Optional: add icon file
)
```

### Result
- **File**: `dist/Datamosh-GUI.exe` (~150-200 MB)
- **Usage**: Double-click to run
- **Compatible**: Windows 10/11 (64-bit)

---

## macOS (App Bundle / DMG)

### Prerequisites (on macOS)
- Python 3.10+ (preferably from python.org, not Homebrew)
- Xcode Command Line Tools: `xcode-select --install`

### Build Steps

```bash
# Install dependencies
pip3 install -r requirements.txt
pip3 install pyinstaller

# Build .app bundle
pyinstaller --onefile --windowed --name "Datamosh GUI" \
    --add-data "README.md:." \
    --add-data "LICENSE:." \
    --hidden-import=PIL._tkinter_finder \
    --hidden-import=tkinterdnd2 \
    --hidden-import=cv2 \
    --osx-bundle-identifier=com.glitches.datamosh-gui \
    mosh_gui.py

# Or use the spec file
pyinstaller --clean datamosh-gui-macos.spec
```

### Create DMG (optional)

```bash
# Install create-dmg
brew install create-dmg

# Create DMG
create-dmg \
  --volname "Datamosh GUI" \
  --window-pos 200 120 \
  --window-size 600 400 \
  --icon-size 100 \
  --icon "Datamosh GUI.app" 175 120 \
  --hide-extension "Datamosh GUI.app" \
  --app-drop-link 425 120 \
  "Datamosh-GUI-macOS.dmg" \
  "dist/Datamosh GUI.app"
```

### macOS Spec File (datamosh-gui-macos.spec)

```python
# -*- mode: python ; coding: utf-8 -*-
block_cipher = None

a = Analysis(
    ['mosh_gui.py'],
    pathex=[],
    binaries=[],
    datas=[('README.md', '.'), ('LICENSE', '.')],
    hiddenimports=['PIL._tkinter_finder', 'tkinterdnd2', 'cv2'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'numpy.testing', 'scipy', 'pandas'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Datamosh GUI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

app = BUNDLE(
    exe,
    name='Datamosh GUI.app',
    icon=None,  # Optional: add icon file
    bundle_identifier='com.glitches.datamosh-gui',
    info_plist={
        'NSPrincipalClass': 'NSApplication',
        'NSHighResolutionCapable': 'True',
    },
)
```

### Result
- **File**: `dist/Datamosh GUI.app` or `Datamosh-GUI-macOS.dmg`
- **Usage**: Drag to Applications folder, then launch
- **Compatible**: macOS 10.15+ (Catalina and newer)

---

## File Sizes (Approximate)

| Platform | Format | Size | Notes |
|----------|--------|------|-------|
| Linux | AppImage | ~103 MB | Includes OpenCV, PIL, all deps |
| Windows | EXE | ~150-200 MB | Single executable, no install |
| macOS | App/DMG | ~120-180 MB | Native .app bundle |

---

## Troubleshooting

### Missing ffmpeg
The executables don't include ffmpeg. Users need to install it separately:

**Linux**: `sudo apt install ffmpeg`
**Windows**: Download from ffmpeg.org and add to PATH
**macOS**: `brew install ffmpeg`

### Python not found (Windows)
- Install Python from python.org (not Microsoft Store version)
- Check "Add Python to PATH" during installation

### Permission denied (Linux/macOS)
```bash
chmod +x Datamosh-GUI-x86_64.AppImage  # Linux
chmod +x dist/Datamosh\ GUI.app/Contents/MacOS/Datamosh\ GUI  # macOS
```

### Gatekeeper warning (macOS)
```bash
# Allow unsigned app
sudo xattr -r -d com.apple.quarantine dist/Datamosh\ GUI.app
```

---

## Cross-Platform Build (Advanced)

For building all platforms from a single machine, consider:

1. **GitHub Actions** - Automated builds for all platforms
2. **Docker** - Build Linux versions in containers
3. **Wine** - Build Windows EXE on Linux (experimental)

---

## Contributing

If you successfully build for a platform not covered here, please contribute to this document!

# Build Instructions

This guide covers packaging the current PySide6 application (`main.py`) for Linux, Windows, and macOS.

## Prerequisites

- Python 3.10+
- `ffmpeg` and `ffprobe` installed on target systems
- Python deps installed: `pip install -r requirements.txt`
- PyInstaller: `pip install pyinstaller`

## Quick Local Sanity Check

Run before packaging:

```bash
QT_QPA_PLATFORM=offscreen pytest -q
python3 main.py
```

## Linux

Build one-folder bundle:

```bash
pyinstaller --noconfirm --clean --windowed --name Datamosh \
  --add-data "README.md:." \
  --add-data "LICENSE:." \
  main.py
```

Output:

- `dist/Datamosh/`

Build Linux installer artifacts:

```bash
./packaging/linux/build_deb.sh "$(cat VERSION)" "dist/Datamosh" "release-artifacts"
./packaging/linux/build_appimage.sh "$(cat VERSION)" "dist/Datamosh" "release-artifacts"
```

Additional output:

- `release-artifacts/Datamosh-<version>-linux-installer.deb`
- `release-artifacts/Datamosh-<version>-linux-<arch>.AppImage`

Run packaged app:

```bash
./dist/Datamosh/Datamosh
```

## Windows (run on Windows)

```powershell
pyinstaller --noconfirm --clean --windowed --name Datamosh `
  --add-data "README.md;." `
  --add-data "LICENSE;." `
  main.py
```

Output:

- `dist/Datamosh/Datamosh.exe`

## macOS (run on macOS)

```bash
pyinstaller --noconfirm --clean --windowed --name Datamosh \
  --add-data "README.md:." \
  --add-data "LICENSE:." \
  --osx-bundle-identifier com.datamosh.gui \
  main.py
```

Output:

- `dist/Datamosh.app`

## Important Packaging Notes

- Do not package `legacy/` as runtime entrypoint; active app starts from `main.py`.
- `ffmpeg`/`ffprobe` are external dependencies and should be documented for end users.
- If startup fails on a target machine, validate:
  - Python runtime and Qt platform plugins included by PyInstaller
  - `ffmpeg -version` and `ffprobe -version` available in `PATH`

## Optional: Reproducible Build Steps

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller
QT_QPA_PLATFORM=offscreen pytest -q
pyinstaller --noconfirm --clean --windowed --name Datamosh main.py
```

## Automated Tagged Releases

Cross-platform release packaging is automated in:

- `.github/workflows/release.yml`

Push a tag like `v1.2.0` or `v1.2.0-beta.1` to build and publish release assets automatically.

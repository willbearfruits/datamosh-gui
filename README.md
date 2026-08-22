# Datamosh GUI

Drop I-frames, duplicate P-frames, and watch the compression tear. A timeline
editor that manipulates the AVI bitstream directly — no re-encoding, no decoding,
just the glitch.

![A clip datamoshing: clean footage dissolving into streaked, smeared colour as the I-frames are removed](assets/showcase/preview-loop.gif)

**[Download for Linux, Windows or macOS →](https://github.com/willbearfruits/datamosh-gui/releases/latest)** ·
[Website](https://willbearfruits.github.io/datamosh-gui/) ·
[Sample output (AVI)](assets/showcase/example-1.avi)

## What This App Does

Datamosh GUI is a PySide6 desktop editor built for experimental compression-art workflows.

![The editor: clip bin on the left, moshed preview in the centre, per-clip keyframe and duplication settings on the right, and a frame-level timeline underneath](assets/showcase/ui-preview.png)

- Build a sequence from multiple clips on a timeline
- Drag clips from bin to timeline, reorder segments, and cut at playhead (snaps to frames)
- **Per-segment glitch settings**: each timeline segment can override the clip's
  keep/duplicate/keyframe settings, so the same clip can appear twice moshed differently
- Toggle "Drop first I-frame" on individual cuts/segments
- Duplicate P-frames to push motion-smear and prediction artifacts
- Preview timeline output before final render
- **Export** to AVI (native Xvid), or **MP4/MOV** (H.264, re-encoded for easy sharing)
- **Save/open projects** as `.dmosh` files (clips, timeline, and settings)
- Undo/redo timeline and settings changes

The app keeps AVI bitstream manipulation in `mosh.py` and uses the GUI as an editor/orchestrator.

## Project Layout

- `main.py`: GUI entrypoint
- `gui/`: active PySide6 application
- `mosh.py`: core AVI parser/rewriter + CLI
- `tests/`: pytest suite
- `legacy/`: old Tkinter-era code (reference only, not active)

## Requirements

- Python 3.10+
- `ffmpeg` and `ffprobe` available on `PATH`

Install Python deps:

```bash
pip install -r requirements.txt
```

## Run

```bash
python3 main.py
```

Or use:

```bash
./launch.sh
```

## Releases & Local Packaging

- Latest release: <https://github.com/willbearfruits/datamosh-gui/releases/latest>
- Download portal: `https://willbearfruits.github.io/datamosh-gui/`
- Release pipeline: `.github/workflows/release.yml`
- Packaging details: `RELEASES.md`

Local build output naming (Linux host):

- `local-release-artifacts/Datamosh-<version>-linux-portable.tar.gz`
- `local-release-artifacts/Datamosh-<version>-linux-installer.deb`
- `local-release-artifacts/Datamosh-<version>-linux-<arch>.AppImage`
- `local-release-artifacts/SHA256SUMS-linux.txt`

Cross-platform local attempt logs (Linux host):

- `local-release-artifacts/windows-build-attempt.log`
- `local-release-artifacts/macos-build-attempt.log`

## Build Locally

Use native OS runners for release-quality builds. Linux can package Linux artifacts locally; Windows and macOS should be built on their own platforms.

Linux:

```bash
pyinstaller --noconfirm --clean --windowed --name Datamosh \
  --add-data "README.md:." \
  --add-data "LICENSE:." \
  --add-data "VERSION:." \
  main.py
./packaging/linux/build_deb.sh "$(cat VERSION)" "dist/Datamosh" "local-release-artifacts"
./packaging/linux/build_appimage.sh "$(cat VERSION)" "dist/Datamosh" "local-release-artifacts"
```

Windows (PowerShell, run on Windows):

```powershell
pyinstaller --noconfirm --clean --windowed --name Datamosh `
  --add-data "README.md;." `
  --add-data "LICENSE;." `
  --add-data "VERSION;." `
  main.py
```

macOS (run on macOS):

```bash
pyinstaller --noconfirm --clean --windowed --name Datamosh \
  --add-data "README.md:." \
  --add-data "LICENSE:." \
  --add-data "VERSION:." \
  --osx-bundle-identifier com.datamosh.gui \
  main.py
```

## Workflow (GUI)

1. Open one or more source clips.
2. Choose import mode/settings (normalize recommended, direct-AVI optional advanced).
3. Wait for ingest/normalization to complete.
4. Drag clips from bin to timeline and reorder as needed.
5. Use playhead + `Cut` (`Ctrl+K`) to split timeline segments.
6. Inject a one-frame I-frame clip from image/video (`Ctrl+Shift+I`) when needed.
7. Toggle `Drop I` (`I`) for selected segment when needed.
8. Adjust per-clip/segment settings:
   - Keep extra keyframes after first
   - Duplicate count
   - Duplicate gap
   - Keep/drop specific keyframe indices
9. Preview timeline output.
10. Render final AVI.

## Keyboard Shortcuts

- `Ctrl+N`: new project
- `Ctrl+Shift+P`: open project (`.dmosh`)
- `Ctrl+S`: save project
- `Ctrl+Shift+S`: save project as
- `Ctrl+O`: open clips
- `Ctrl+Shift+O`: add clips
- `Ctrl+R`: render
- `Ctrl+Z`: undo
- `Ctrl+Shift+Z` / `Ctrl+Y`: redo
- `Space`: play/pause preview
- `Left` / `Right`: frame step
- `Ctrl+K`: cut selected timeline segment at playhead
- `Ctrl+Shift+I`: inject single I-frame clip from media
- `I`: toggle drop-first I-frame for selected segment
- `Delete`: remove selected timeline segment
- `F1`: shortcut help

## CLI (Core Engine)

`mosh.py` is usable directly for scripted workflows:

```bash
python3 mosh.py input.avi output.avi --keep-first 1 --duplicate-count 2 --duplicate-gap 3
```

Normalization example:

```bash
python3 mosh.py input.mp4 output.avi --normalize --normalize-preset balanced
```

## Testing

Headless-safe full suite:

```bash
QT_QPA_PLATFORM=offscreen pytest -q
```

## Projects

Save your whole session — clips, per-clip mosh settings, timeline arrangement, cuts,
and injected I-frames — to a `.dmosh` project file (`File > Save Project`, `Ctrl+S`).
Reopening (`File > Open Project`, `Ctrl+Shift+P`) recreates the clips from their source
paths and re-ingests them, so projects stay small and portable. Source media must still
be present at its saved path; missing sources are reported and left empty. The window
title shows the project name and a `*` when there are unsaved changes.

## Changelog

Current version `v1.2.0` — save/open `.dmosh` projects, per-segment glitch settings,
and MP4/MOV export. Full history in [CHANGELOG.md](CHANGELOG.md), downloads on the
[releases page](https://github.com/willbearfruits/datamosh-gui/releases).

## Support

If this project helps your workflow, support ongoing development and experiments:

- Patreon: <https://www.patreon.com/Seriousshit>
- PayPal: <https://www.paypal.com/cgi-bin/webscr?cmd=_donations&business=dogme84%40gmail.com&currency_code=USD>

## Notes

- Renders to AVI/Xvid natively, or MP4/MOV (H.264) when you need something shareable.
- Non-AVI sources are normalized before processing.
- `legacy/` exists for historical reference; active code path is `main.py` + `gui/`.

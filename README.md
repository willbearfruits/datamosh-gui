# Datamosh GUI

**Interactive video datamoshing tool with real-time preview**

A professional-grade GUI application for creating datamosh glitch effects by manipulating I-frames and P-frames in video files. Built with Python and Tkinter.

---

## Features

- **GUI Interface**: Easy-to-use Tkinter interface for non-technical users
- **Real-Time Preview**: Stream frames directly from ffmpeg to preview glitch effects
- **Multiple Clips**: Append multiple video clips for complex datamosh sequences
- **Flexible Keyframe Control**:
  - Keep/drop specific keyframes by index
  - Drop first keyframe of appended clips
  - Keep initial N keyframes
- **P-Frame Duplication**: Duplicate P-frames at custom intervals for enhanced glitch
- **Video Normalization**: Built-in presets (Fast, Balanced, Sharp) for optimal moshing
- **Custom Settings**: Per-clip configuration for advanced control
- **Audio Support**: Preserve original audio or strip it during processing

---

## Screenshots

*Coming soon*

---

## Requirements

### System Dependencies
- **Python**: 3.10 or higher
- **ffmpeg**: Required for video processing (must be in PATH)

### Python Dependencies
- **Pillow**: For inline preview window (optional but recommended)
- **tkinter**: Usually included with Python

---

## Installation

### Quick Setup

```bash
# Clone or download this repository
cd datamosh-gui

# Install Python dependencies
pip install -r requirements.txt

# Ensure ffmpeg is installed
ffmpeg -version

# Run the GUI
python3 mosh_gui.py
```

### Install ffmpeg (if not already installed)

**Ubuntu/Debian:**
```bash
sudo apt install ffmpeg
```

**macOS (Homebrew):**
```bash
brew install ffmpeg
```

**Windows:**
Download from https://ffmpeg.org/download.html and add to PATH

---

## Usage

### GUI Mode (Recommended)

1. **Launch the GUI:**
   ```bash
   python3 mosh_gui.py
   ```

2. **Load a base clip:**
   - Click "Browse..." next to "Input clip"
   - Select your source video
   - Choose normalization preset (Balanced recommended)

3. **Configure settings:**
   - **Keep first I-frames**: Number of keyframes to preserve (default: 1)
   - **Duplicate count**: How many times to duplicate P-frames (0-99)
   - **Duplicate gap**: Duplicate every Nth P-frame
   - **Drop first keyframe**: Remove the first keyframe of appended clips

4. **Add more clips (optional):**
   - Click "Add append..." to load additional clips
   - Each clip can have independent settings

5. **Preview or Render:**
   - Click "Preview" to see the effect without saving
   - Click "Render" to export the final moshed video

### CLI Mode

```bash
# Basic datamosh
python3 mosh.py input.avi output.avi --keep-first 1

# With normalization
python3 mosh.py input.mp4 output.avi --normalize --normalize-preset balanced

# Duplicate P-frames
python3 mosh.py input.avi output.avi --duplicate-count 3 --duplicate-gap 2

# Append multiple clips
python3 mosh.py base.avi output.avi --append clip1.avi --append clip2.avi --normalize

# Advanced keyframe control
python3 mosh.py input.avi output.avi --keep-keys "0,5,10-15" --drop-keys "20-25"
```

---

## How Datamoshing Works

Datamoshing is a glitch art technique that manipulates compressed video by removing I-frames (keyframes) and/or duplicating P-frames (predicted frames):

1. **I-frames**: Complete images that can be decoded independently
2. **P-frames**: Difference frames that rely on previous frames for prediction

By removing I-frames, subsequent P-frames have no reference point and create prediction errors that cascade through the video, resulting in:
- Bleeding colors and textures
- Motion trails and ghosting effects
- Abstract, painterly distortions

---

## Presets

| Preset | Resolution | Quality | GOP | Use Case |
|--------|------------|---------|-----|----------|
| **Fast** | 960px | Medium | 60 | Quick previews, experimental |
| **Balanced** | 1280px | Good | 48 | General use (recommended) |
| **Sharp** | 1920px | High | 36 | High-quality exports |
| **Original** | Native | N/A | N/A | Use source video as-is |
| **Custom** | User-defined | User-defined | User-defined | Fine-tuned control |

---

## Technical Details

### Supported Formats

- **Input**: Any format supported by ffmpeg (MP4, MOV, MKV, AVI, etc.)
- **Processing**: Xvid-encoded AVI (automatically normalized)
- **Output**: AVI (compatible with most video editors)

### Performance

- GUI uses threading for non-blocking operations
- Preview streams frames at ~67fps (15ms interval)
- Normalization speed depends on video size and CPU

### Architecture

- **mosh_gui.py**: Tkinter GUI with preview streaming
- **mosh.py**: Core AVI manipulation engine (works standalone)
- Binary-level RIFF/AVI parsing for precise control

---

## Tips for Best Results

1. **Start simple**: Use "Balanced" preset with default settings
2. **Preview first**: Always preview before rendering long videos
3. **Experiment with P-frame duplication**: Try values 1-5 for different effects
4. **Append clips strategically**: Drop first keyframe of appends for smooth transitions
5. **Keep audio**: Preserve audio for context, or remove for pure visual glitch
6. **Source footage matters**: High-motion videos create more dramatic effects

---

## Troubleshooting

### "ffmpeg not found"
- Install ffmpeg and ensure it's in your system PATH
- Or specify custom path in GUI: ffmpeg section

### "Pillow is not installed"
- GUI will fallback to external ffplay for preview
- Install Pillow for inline preview: `pip install Pillow`

### Preview window is small/pixelated
- Preview is scaled to 480px width for performance
- Final render uses full resolution from preset

### Glitch effect too subtle
- Increase duplicate count
- Drop more keyframes (reduce "Keep first I-frames")
- Try different source footage with more motion

---

## Development

### Project Structure

```
datamosh-gui/
├── mosh_gui.py          # GUI application
├── mosh.py              # Core datamosh engine
├── requirements.txt     # Python dependencies
├── README.md            # This file
├── LICENSE              # MIT License
└── .gitignore          # Git ignore patterns
```

### Contributing

Contributions welcome! Areas for improvement:
- [ ] Package as standalone executable (PyInstaller)
- [ ] Add application icon
- [ ] Save/load project files
- [ ] Batch processing mode
- [ ] Additional export formats (MP4, WebM)
- [ ] Preset manager
- [ ] Keyboard shortcuts
- [ ] Progress bar for rendering

---

## License

MIT License - see [LICENSE](LICENSE) file for details

---

## Credits

- **Core algorithm**: Binary AVI manipulation and RIFF parsing
- **GUI framework**: Python Tkinter
- **Video processing**: ffmpeg (external dependency)
- **Inspiration**: Glitch art community and datamosh pioneers

---

## Examples

### Basic Glitch
```bash
python3 mosh_gui.py
# Load a video, use Balanced preset, keep 1 keyframe, render
```

### Extreme Duplication
```bash
python3 mosh.py input.avi extreme.avi --normalize --duplicate-count 10 --duplicate-gap 1
```

### Multi-Clip Sequence
```bash
python3 mosh.py base.avi sequence.avi --append clip1.avi --append clip2.avi --normalize --normalize-preset sharp
```

---

**Have fun glitching!**

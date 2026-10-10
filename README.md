# SnipBG

A simple desktop app for Windows that removes photo backgrounds **entirely on your own
computer**. Nothing is uploaded. It uses the **InSPyReNet** model (via
[`transparent-background`](https://github.com/plemeri/transparent-background)), which
handles hair and fine edges well.

## Download

Grab the latest version from the [Releases page](https://github.com/KeithClemmons/SnipBG/releases):

- **`SnipBG-Setup-x.y.z.exe`**: installer (recommended). No admin rights needed. Adds a Start menu entry and an uninstaller.
- **`SnipBG-x.y.z-portable.zip`**: unzip anywhere and run `SnipBG.exe`.

Windows may show a SmartScreen warning because the app isn't code-signed. Click **More info → Run anyway**.
The AI model (~150 MB) downloads automatically the first time you remove a background.

## How to use it

1. **Drop** photos or folders onto the window (or click the drop area to browse).
2. **Pick a background**: None (transparent), White, Black, a color, a blur of the original, or another photo.
3. Click **Remove background**. Results are saved to the folder shown under **Save to**. Click **Open** to see them.

After a photo has been processed, changing the background or effects updates the
preview instantly. Use **Before / After** to compare, and the arrow keys to move
between photos. Right-click a thumbnail to remove it or show its saved file.

### More options

These are hidden under **More options** until you need them:

| Group | Options |
|---|---|
| Quality | Best / Fast model, GPU (NVIDIA) |
| Effects | Drop shadow, shadow style, clean edges (despill), center subject, sticker outline |
| Size | AI upscale 2×/3×/4×, resize to an exact size |
| Output file | PNG / WebP, file size, file naming, save alpha mask, watermark |
| Video & GIF | Frames to process, MOV (transparent ProRes) or MP4 (green screen) |

Your settings and output folder are remembered between runs.

## Running from source

### Setup (one time)

1. Install **Python 3.10 or 3.11** from https://www.python.org/downloads/ and tick **"Add Python to PATH"**.
2. Double-click **`setup.bat`**. It creates a local `.venv` and installs PyTorch (CPU) and the other dependencies.

The AI model (~150 MB) downloads automatically the first time you remove a background.

Optional extras:
- **AI upscaling:** run `install_upscale.bat` (Real-ESRGAN). Without it, upscaling falls back to Lanczos + sharpening.
- **Video:** install ffmpeg with `winget install Gyan.FFmpeg`. GIFs work without it.

### Running it

- Double-click **`SnipBG.vbs`** (no console window), or **`run.bat`**.
- **`make_shortcut.bat`** puts a shortcut with the icon on your Desktop. Right-click it and choose **Pin to taskbar**.
- **`build_exe.bat`** builds a standalone `dist\SnipBG\SnipBG.exe` with PyInstaller.

### Right-click menu

`install_context_menu.bat` adds **Remove background (SnipBG)** to Explorer's right-click
menu for images. `uninstall_context_menu.bat` removes it.

### Command line

```
snipbg-cli photo.jpg -o output
snipbg-cli ./photos -o output --background white --compression lossless
snipbg-cli portrait.jpg -o output --background blur --blur-strength 70
snipbg-cli logo.png -o output --sticker --sticker-color black
```

Run `snipbg-cli --help` for every option.

## Making a release

1. Bump `APP_VERSION` in `app.py`, then commit.
2. Run **`build_installer.bat`**. It builds the .exe, self-tests it on a clean profile, and writes
   the installer and portable zip to `installer\`. It needs Inno Setup: `winget install JRSoftware.InnoSetup`.
3. Publish them as a GitHub release:

```
gh release create v1.0.0 installer\SnipBG-Setup-1.0.0.exe installer\SnipBG-1.0.0-portable.zip --title "SnipBG 1.0.0" --generate-notes
```

## Project layout

| File | Purpose |
|---|---|
| `app.py` | Desktop app (Tkinter) |
| `core.py` | Image pipeline: cutout, despill, upscale, sticker, shadow, background, resize, watermark, saving |
| `video.py` | GIF and video processing |
| `batch.py` | Batch runner shared by the CLI |
| `cli.py` | Command-line interface |
| `config.py` | Remembers settings in `~/.snipbg/config.json` |

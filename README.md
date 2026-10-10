# SnipBG

A simple desktop app for Windows that removes photo backgrounds **entirely on your own
computer**. Nothing is uploaded. It uses the **InSPyReNet** model (via
[`transparent-background`](https://github.com/plemeri/transparent-background)), which
handles hair and fine edges well.

## Download

Get the latest version from the [Releases page](https://github.com/KeithClemmons/SnipBG/releases):

| System | File |
|---|---|
| **Windows** | `SnipBG-Setup-x.y.z.exe` (installer, no admin rights needed) or `SnipBG-x.y.z-windows-portable.zip` |
| **Mac** (Apple Silicon: M1 or newer) | `SnipBG-x.y.z-macos-arm64.dmg`: open it and drag SnipBG to Applications |
| **Linux** (x86-64) | `SnipBG-x.y.z-linux-x86_64.tar.gz`: extract it and run `SnipBG/SnipBG`. `install.sh` adds it to your app menu. |

The app isn't code-signed, so the first launch shows a warning:
- **Windows:** "Windows protected your PC". Click **More info → Run anyway**.
- **Mac:** macOS blocks the app. Go to **System Settings → Privacy & Security** and click **Open Anyway**.

The AI model (~350 MB) downloads automatically the first time you remove a background.

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

### Setup on Windows (one time)

1. Install **Python 3.10 or 3.11** from https://www.python.org/downloads/ and tick **"Add Python to PATH"**.
2. Double-click **`setup.bat`**. It creates a local `.venv` and installs PyTorch (CPU) and the other dependencies.

The AI model (~350 MB) downloads automatically the first time you remove a background.

Optional extras:
- **AI upscaling:** run `install_upscale.bat` (Real-ESRGAN). Without it, upscaling falls back to Lanczos + sharpening.
- **Video:** install ffmpeg with `winget install Gyan.FFmpeg`. GIFs work without it.

### Setup on macOS / Linux

```
python3 -m venv .venv
.venv/bin/pip install torch torchvision    # Linux: add --index-url https://download.pytorch.org/whl/cpu
.venv/bin/pip install -r requirements.txt
.venv/bin/python app.py
```

### Running it (Windows)

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

Releases are built by GitHub Actions ([`.github/workflows/release.yml`](.github/workflows/release.yml))
on Windows, macOS and Linux. Each build is self-tested on a clean profile before anything is published.

1. Bump `APP_VERSION` in `app.py` and commit.
2. Tag and push:

```
git tag v1.1.0
git push origin main v1.1.0
```

The release appears on the Releases page about 20–30 minutes later. To build and test without
publishing, use **Run workflow** on the repo's Actions tab.

Building locally: `build_installer.bat` on Windows (needs Inno Setup: `winget install JRSoftware.InnoSetup`)
or `./build_release.sh` on macOS/Linux. Both write to `installer/`. Library versions for releases are
pinned in `constraints.txt`.

## Project layout

| File | Purpose |
|---|---|
| `app.py` | Desktop app (Tkinter) |
| `core.py` | Image pipeline: cutout, despill, upscale, sticker, shadow, background, resize, watermark, saving |
| `video.py` | GIF and video processing |
| `batch.py` | Batch runner shared by the CLI |
| `cli.py` | Command-line interface |
| `config.py` | Remembers settings in `~/.snipbg/config.json` |

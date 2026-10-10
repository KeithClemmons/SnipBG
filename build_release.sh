#!/usr/bin/env bash
# Build SnipBG release files on macOS or Linux (the Windows equivalent is build_installer.bat).
#   1. Builds the app with PyInstaller
#   2. Self-tests it on a clean home folder (catches missing bundled files)
#   3. Packages it into installer/:
#        macOS: SnipBG-<version>-macos-<arch>.dmg
#        Linux: SnipBG-<version>-linux-<arch>.tar.gz
# Usage: ./build_release.sh            (uses .venv/bin/python)
#        PYTHON=python3 ./build_release.sh
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-.venv/bin/python}"
VER=$("$PYTHON" -c 'import re;print(re.search(r"APP_VERSION = \"(.+?)\"", open("app.py").read()).group(1))')
ARCH=$(uname -m)
echo "Building SnipBG $VER ($(uname -s) $ARCH)"

"$PYTHON" -m PyInstaller --noconfirm --clean SnipBG.spec

if [[ "$(uname -s)" == "Darwin" ]]; then
  EXE="dist/SnipBG.app/Contents/MacOS/SnipBG"
else
  EXE="dist/SnipBG/SnipBG"
fi

echo "Self-testing the packaged app on a clean home folder..."
TESTHOME=$(mktemp -d)
mkdir -p "$TESTHOME/.transparent-background"
# Reuse downloaded model weights so the test doesn't re-download them, but leave out
# config.yaml so the bundled copy gets used.
if [[ -f "$HOME/.transparent-background/ckpt_base.pth" ]]; then
  cp "$HOME/.transparent-background/ckpt_base.pth" "$TESTHOME/.transparent-background/"
fi
if ! HOME="$TESTHOME" SNIPBG_SELFTEST="$PWD/snipbg.png|$TESTHOME/out" "$EXE"; then
  echo "SELF-TEST FAILED:"
  cat "$TESTHOME/out/selftest_error.txt" 2>/dev/null || true
  exit 1
fi
[[ -f "$TESTHOME/out/selftest.png" ]] || { echo "SELF-TEST FAILED: no output written"; exit 1; }
echo "Self-test passed."
rm -rf "$TESTHOME"

mkdir -p installer
if [[ "$(uname -s)" == "Darwin" ]]; then
  OUT="installer/SnipBG-$VER-macos-$ARCH.dmg"
  STAGE=$(mktemp -d)
  cp -R dist/SnipBG.app "$STAGE/"
  ln -s /Applications "$STAGE/Applications"
  rm -f "$OUT"
  hdiutil create -volname "SnipBG $VER" -srcfolder "$STAGE" -ov -format UDZO "$OUT"
  rm -rf "$STAGE"
else
  # Small helper so Linux users can add SnipBG to their app menu.
  cat > dist/SnipBG/install.sh <<'EOS'
#!/usr/bin/env bash
# Adds SnipBG to your applications menu (run from inside the extracted SnipBG folder).
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p ~/.local/share/applications
cat > ~/.local/share/applications/snipbg.desktop <<EOF
[Desktop Entry]
Type=Application
Name=SnipBG
Comment=Remove photo backgrounds offline
Exec="$DIR/SnipBG"
Icon=$DIR/_internal/snipbg.png
Categories=Graphics;
Terminal=false
EOF
echo "SnipBG added to your applications menu."
EOS
  chmod +x dist/SnipBG/install.sh
  OUT="installer/SnipBG-$VER-linux-$ARCH.tar.gz"
  tar -czf "$OUT" -C dist SnipBG
fi
echo "Wrote $OUT ($(du -h "$OUT" | cut -f1))"

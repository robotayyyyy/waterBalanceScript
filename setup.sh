#!/usr/bin/env bash
set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FORE_DIR="$ROOT_DIR/swat_forecast"
HIST_DIR="$ROOT_DIR/historical_data"

echo "=== [1/5] Check python3-venv ==="
MISSING_PKGS=()
python3 -m venv --help > /dev/null 2>&1 || MISSING_PKGS+=(python3-venv python3-pip)
command -v unzip > /dev/null 2>&1 || MISSING_PKGS+=(unzip)
if [ ${#MISSING_PKGS[@]} -gt 0 ]; then
    echo "Installing missing packages: ${MISSING_PKGS[*]} (requires sudo)..."
    sudo apt-get install -y "${MISSING_PKGS[@]}"
fi

echo "=== [2/5] Create forecast venv ==="
python3 -m venv "$FORE_DIR/env"
"$FORE_DIR/env/bin/pip" install --upgrade pip -q
"$FORE_DIR/env/bin/pip" install -r "$FORE_DIR/requirements.txt" -q
echo "    OK: $FORE_DIR/env"

echo "=== [3/5] Create historical venv ==="
python3 -m venv "$HIST_DIR/env"
"$HIST_DIR/env/bin/pip" install --upgrade pip -q
"$HIST_DIR/env/bin/pip" install -r "$HIST_DIR/requirements.txt" -q
echo "    OK: $HIST_DIR/env"

echo "=== [4/5] Download zips from Google Drive ==="
"$FORE_DIR/env/bin/pip" install -q gdown
make -C "$ROOT_DIR" download-drive

echo "=== [5/5] Unpack TxtInOut + swat_rev688 ==="
make -C "$ROOT_DIR" unpack-all

echo "=== Fix SWAT executable permissions ==="
chmod +x "$FORE_DIR/swat_rev688/rev688_64rel_linux"
chmod +x "$FORE_DIR/swat_rev688/rev688_64debug_linux"

echo ""
echo "Setup complete."
echo "  make check-db        # verify DB connection"
echo "  make run-week-yom    # run weekly pipeline"
echo "  make run-month-yom   # run monthly pipeline"

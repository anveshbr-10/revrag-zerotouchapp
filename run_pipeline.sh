#!/usr/bin/env bash
#
# run_pipeline.sh
#
# End-to-end orchestration for the Zero-Touch App Understanding pipeline:
#   1. Pull the raw exploration dump off the connected device/emulator
#      (written there by AppExplorer.kt during `./gradlew connectedAndroidTest`).
#   2. Run perceiver.py to turn each unique screen into structured JSON via
#      a local Ollama vision model.
#   3. Run synthesizer.py to merge everything into app_knowledge_pack.json.
#   4. Run report.py to produce a human-readable button/screen report.
#
# Usage:
#   ./run_pipeline.sh [device-serial]
#
# Assumes:
#   - adb is on PATH and exactly one device/emulator is connected (or pass its
#     serial as the first argument, from `adb devices`).
#   - AppExplorer.kt has already been run against the target app via
#     `./gradlew connectedAndroidTest`, so /sdcard/knowledge_pack/raw exists
#     on the device.
#   - Ollama is running locally with the model from perceiver.py pulled
#     (default: qwen2.5vl:7b -- see perceiver.py's MODEL_NAME).

set -euo pipefail

SERIAL="${1:-}"
ADB=(adb)
if [[ -n "$SERIAL" ]]; then
  ADB=(adb -s "$SERIAL")
fi

DEVICE_DIR="/sdcard/knowledge_pack"
LOCAL_DIR="knowledge_pack"

echo "==> Pulling raw exploration data from device ($DEVICE_DIR/raw)..."
mkdir -p "$LOCAL_DIR"
rm -rf "$LOCAL_DIR/raw"
"${ADB[@]}" pull "$DEVICE_DIR/raw" "$LOCAL_DIR/raw"

echo "==> Running perceiver (screenshots + tree -> structured JSON per screen)..."
python3 perceiver.py --raw-dir "$LOCAL_DIR/raw" --out-dir "$LOCAL_DIR/perceived"

echo "==> Running synthesizer (merge into app_knowledge_pack.json)..."
python3 synthesizer.py \
  --perceived-dir "$LOCAL_DIR/perceived" \
  --raw-dir "$LOCAL_DIR/raw" \
  --out-file "$LOCAL_DIR/app_knowledge_pack.json"

echo "==> Generating human-readable report..."
python3 report.py \
  --pack-file "$LOCAL_DIR/app_knowledge_pack.json" \
  --out-file "$LOCAL_DIR/button_report.md"

echo "==> Building the app map viewer..."
python3 build_viewer.py \
  --pack-file "$LOCAL_DIR/app_knowledge_pack.json" \
  --out-file "$LOCAL_DIR/viewer.html"

echo "==> Building the rebuild test (2-3 screens from the pack alone)..."
python3 rebuild_test.py \
  --pack-file "$LOCAL_DIR/app_knowledge_pack.json" \
  --out-file "$LOCAL_DIR/rebuild_test.html" \
  --count 3

echo ""
echo "Done. See:"
echo "  - $LOCAL_DIR/app_knowledge_pack.json  (machine-facing pack, for an agent)"
echo "  - $LOCAL_DIR/button_report.md         (human-readable report)"
echo "  - $LOCAL_DIR/viewer.html              (app map: screenshot + profile per screen)"
echo "  - $LOCAL_DIR/rebuild_test.html         (rebuild-from-pack-alone comparison)"
echo ""
echo "For the dark-mode verdict and the stability check, see dark_mode_check.py and"
echo "compare_packs.py respectively (each is a second exploration pass, so they aren't"
echo "part of this single-run pipeline) -- both are documented in README.md."

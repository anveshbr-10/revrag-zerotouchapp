"""
dark_mode_check.py

Compares two already-synthesized App Knowledge Packs -- one captured with the
device's system dark-mode setting off, one with it forced on -- and folds a
supports_dark_mode verdict (plus the dark-mode palette, for reference) into
the design section of the final pack.

This is a separate pass rather than something synthesizer.py can infer on its
own: dark-mode support can only be observed by literally re-running the
exploration with the device's UI mode toggled, which is a second on-device
capture, not something derivable from a single raw dump.

Typical flow:
    adb shell cmd uimode night no
    ./gradlew connectedAndroidTest \
        -Pandroid.testInstrumentationRunnerArguments.raw_subdir=light
    adb pull /sdcard/knowledge_pack/raw_light knowledge_pack/raw_light
    python perceiver.py   --raw-dir knowledge_pack/raw_light --out-dir knowledge_pack/perceived_light
    python synthesizer.py --perceived-dir knowledge_pack/perceived_light \
                           --raw-dir knowledge_pack/raw_light \
                           --out-file knowledge_pack/app_knowledge_pack_light.json

    adb shell cmd uimode night yes
    ./gradlew connectedAndroidTest \
        -Pandroid.testInstrumentationRunnerArguments.raw_subdir=dark
    adb pull /sdcard/knowledge_pack/raw_dark knowledge_pack/raw_dark
    python perceiver.py   --raw-dir knowledge_pack/raw_dark --out-dir knowledge_pack/perceived_dark
    python synthesizer.py --perceived-dir knowledge_pack/perceived_dark \
                           --raw-dir knowledge_pack/raw_dark \
                           --out-file knowledge_pack/app_knowledge_pack_dark.json

    python dark_mode_check.py \
        --light-pack knowledge_pack/app_knowledge_pack_light.json \
        --dark-pack  knowledge_pack/app_knowledge_pack_dark.json \
        --out-file   knowledge_pack/app_knowledge_pack.json

The light-mode pack is treated as the primary pack (its screens/journeys
win); only design.supports_dark_mode and design.colors_dark are added.

Requires: nothing beyond the standard library.
"""

import argparse
import json
from pathlib import Path

LUMINANCE_GAP_THRESHOLD = 25  # 0-255 scale; how much darker the dark pass needs to be


def hex_to_rgb(hex_color: str):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def mean_luminance(colors: list):
    if not colors:
        return None
    total = 0.0
    for c in colors:
        r, g, b = hex_to_rgb(c)
        total += 0.299 * r + 0.587 * g + 0.114 * b
    return total / len(colors)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--light-pack", required=True)
    parser.add_argument("--dark-pack", required=True)
    parser.add_argument("--out-file", default="knowledge_pack/app_knowledge_pack.json")
    args = parser.parse_args()

    light = json.loads(Path(args.light_pack).read_text())
    dark = json.loads(Path(args.dark_pack).read_text())

    light_colors = light.get("design", {}).get("colors", [])
    dark_colors = dark.get("design", {}).get("colors", [])

    light_lum = mean_luminance(light_colors)
    dark_lum = mean_luminance(dark_colors)

    if light_lum is None or dark_lum is None:
        supports_dark_mode = None
        print("Not enough color data in one of the packs -- leaving supports_dark_mode unknown.")
    else:
        supports_dark_mode = (light_lum - dark_lum) >= LUMINANCE_GAP_THRESHOLD
        print(
            f"Light-pass avg luminance: {light_lum:.1f}, dark-pass: {dark_lum:.1f} "
            f"-> supports_dark_mode={supports_dark_mode}"
        )

    light.setdefault("design", {})
    light["design"]["supports_dark_mode"] = supports_dark_mode
    light["design"]["colors_dark"] = dark_colors

    out_file = Path(args.out_file)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(light, indent=2))
    print(f"Wrote {out_file}")


if __name__ == "__main__":
    main()

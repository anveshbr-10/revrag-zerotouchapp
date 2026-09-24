"""
synthesizer.py

Merges everything the Explorer + Perceiver produced into a single, compact
App Knowledge Pack matching our agreed schema: screens[], journeys[], design{}.

Inputs:
  knowledge_pack/perceived/<hash>.json   (one per unique screen, from perceiver.py)
  knowledge_pack/raw/transitions.jsonl   (one line per tap/back, from AppExplorer.kt)
  knowledge_pack/raw/<hash>/tree.xml     (used only for font/spacing hints, if present)

Output:
  knowledge_pack/app_knowledge_pack.json

Design notes:
- Screenshot references are kept as file PATHS, never inlined bytes, so the pack
  stays compact regardless of how many screens were explored.
- Journeys are reconstructed by walking the transition graph from screens with
  no incoming edges (likely entry points) outward, up to a max depth, so you get
  a handful of readable named paths rather than a full edge dump.
- Colors are clustered from a *sample* of screenshots (not all of them) to keep
  this step fast — full accuracy isn't needed for a brand palette summary.

Requires: pip install pillow scikit-learn
"""

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

from PIL import Image
from sklearn.cluster import KMeans

MAX_JOURNEY_DEPTH = 6
MAX_JOURNEYS = 10
COLOR_SAMPLE_SCREENS = 12   # cap how many screenshots we run k-means on
COLOR_CLUSTERS = 6


# ---------- screens ----------

def load_screens(perceived_dir: Path) -> dict:
    """Returns {hash: screen_dict} built directly from perceiver.py output —
    this step trusts that schema rather than re-deriving it."""
    screens = {}
    for f in perceived_dir.glob("*.json"):
        data = json.loads(f.read_text())
        screen_hash = data.pop("_screen_hash", f.stem)
        screens[screen_hash] = {
            "id": screen_hash,
            "purpose": data.get("purpose"),
            "screen_type": data.get("screen_type"),
            "elements": data.get("elements", []),
            "form_fields": data.get("form_fields", []),
            "screenshot_ref": data.get("_screenshot_ref"),
        }
    return screens


# ---------- journeys ----------

def load_transitions(raw_dir: Path) -> list[dict]:
    trans_file = raw_dir / "transitions.jsonl"
    if not trans_file.exists():
        return []
    transitions = []
    for line in trans_file.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line:
            transitions.append(json.loads(line))
    return transitions


def build_journeys(transitions: list[dict], screens: dict) -> list[dict]:
    if not transitions:
        return []

    edges = defaultdict(list)  # from_hash -> [(element_label, to_hash)]
    has_incoming = set()
    for t in transitions:
        if t["element_key"] == "BACK":
            continue  # backing out isn't a forward journey step
        edges[t["from_hash"]].append((t["element_label"], t["to_hash"]))
        has_incoming.add(t["to_hash"])

    entry_points = [h for h in edges if h not in has_incoming] or list(edges.keys())[:1]

    journeys = []
    for start in entry_points[:MAX_JOURNEYS]:
        path_screens = [start]
        path_labels = []
        current = start
        visited_in_path = {start}

        for _ in range(MAX_JOURNEY_DEPTH):
            options = edges.get(current)
            if not options:
                break
            label, nxt = options[0]  # first-discovered edge; good enough for a named path
            if nxt in visited_in_path:
                break  # avoid loops
            path_labels.append(label)
            path_screens.append(nxt)
            visited_in_path.add(nxt)
            current = nxt

        if len(path_screens) > 1:
            name_hint = screens.get(start, {}).get("purpose", start)
            journeys.append({
                "name": f"From: {name_hint}",
                "steps": path_screens,
                "via": path_labels,
            })

    return journeys


# ---------- design rollup ----------

def sample_screenshots(screens: dict, limit: int) -> list[Path]:
    paths = [Path(s["screenshot_ref"]) for s in screens.values() if s.get("screenshot_ref")]
    paths = [p for p in paths if p.exists()]
    return paths[:limit]


def extract_colors(screenshots: list[Path]) -> list[str]:
    if not screenshots:
        return []

    pixels = []
    for path in screenshots:
        img = Image.open(path).convert("RGB").resize((50, 50))  # downsample for speed
        pixels.extend(list(img.getdata()))

    if len(pixels) < COLOR_CLUSTERS:
        return []

    kmeans = KMeans(n_clusters=COLOR_CLUSTERS, n_init=4, random_state=0).fit(pixels)
    hex_colors = [
        "#{:02x}{:02x}{:02x}".format(*[max(0, min(255, round(c))) for c in center])
        for center in kmeans.cluster_centers_
    ]
    return hex_colors


def extract_font_hints(raw_dir: Path) -> list[str]:
    """Best-effort: pull distinct text-size-ish attributes if the tree exposes them.
    Many trees won't have explicit font info — this stays empty rather than guessing."""
    sizes = set()
    for tree_file in raw_dir.glob("*/tree.xml"):
        text = tree_file.read_text()
        for m in re.finditer(r'textSize="([\d.]+)"', text):
            sizes.add(m.group(1))
    return sorted(sizes)


def rollup_design(screens: dict, raw_dir: Path) -> dict:
    # tone_of_voice_sample lives on the raw perceived dict, not the trimmed screen dict
    # (load_screens doesn't copy it over), so it's re-pulled directly from source files.
    tone_samples = []
    for f in (raw_dir.parent / "perceived").glob("*.json"):
        data = json.loads(f.read_text())
        if data.get("tone_of_voice_sample"):
            tone_samples.append(data["tone_of_voice_sample"])

    screenshots = sample_screenshots(screens, COLOR_SAMPLE_SCREENS)

    return {
        "colors": extract_colors(screenshots),
        "fonts": extract_font_hints(raw_dir),
        "spacing_scale": [],
        "components": sorted({el.get("role") for scr in screens.values() for el in scr.get("elements", []) if el.get("role")}),
        "tone_of_voice_samples": tone_samples[:20],
        # Not inferable from a single exploration pass -- set by dark_mode_check.py
        # when both a light-mode and a dark-mode raw dump are available (see that
        # script and README for how to run the two passes).
        "supports_dark_mode": None,
    }


# ---------- main ----------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--perceived-dir", default="knowledge_pack/perceived")
    parser.add_argument("--raw-dir", default="knowledge_pack/raw")
    parser.add_argument("--out-file", default="knowledge_pack/app_knowledge_pack.json")
    args = parser.parse_args()

    perceived_dir = Path(args.perceived_dir)
    raw_dir = Path(args.raw_dir)

    screens = load_screens(perceived_dir)
    print(f"Loaded {len(screens)} screens.")

    transitions = load_transitions(raw_dir)
    journeys = build_journeys(transitions, screens)
    print(f"Built {len(journeys)} journeys from {len(transitions)} transitions.")

    design = rollup_design(screens, raw_dir)
    print(f"Design rollup: {len(design['colors'])} colors, "
          f"{len(design['tone_of_voice_samples'])} tone samples.")

    pack = {
        "screens": list(screens.values()),
        "journeys": journeys,
        "design": design,
    }

    out_file = Path(args.out_file)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(pack, indent=2))

    size_kb = out_file.stat().st_size / 1024
    print(f"\nWrote {out_file} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()

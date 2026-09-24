"""
compare_packs.py

Evidence for the "output must stay stable across repeat scans" requirement:
diffs two app_knowledge_pack.json files produced by separate exploration runs
of the same app and reports how much actually changed.

Screen ids are content hashes (from AppExplorer.kt's structural hash), so a
perfectly stable pair of scans reproduces the same set of ids. This script
reports screens only seen in one run, and for ids present in both, whether
their purpose/elements actually differ.

Usage:
    python compare_packs.py --pack-a knowledge_pack/run1/app_knowledge_pack.json \
                             --pack-b knowledge_pack/run2/app_knowledge_pack.json
"""

import argparse
import json
from pathlib import Path


def load_screens(pack_path: Path) -> dict:
    pack = json.loads(pack_path.read_text())
    return {s["id"]: s for s in pack.get("screens", [])}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack-a", required=True)
    parser.add_argument("--pack-b", required=True)
    args = parser.parse_args()

    screens_a = load_screens(Path(args.pack_a))
    screens_b = load_screens(Path(args.pack_b))

    ids_a, ids_b = set(screens_a), set(screens_b)
    only_a = ids_a - ids_b
    only_b = ids_b - ids_a
    shared = ids_a & ids_b

    changed = [
        sid for sid in shared
        if screens_a[sid].get("purpose") != screens_b[sid].get("purpose")
        or screens_a[sid].get("elements") != screens_b[sid].get("elements")
    ]

    total = len(ids_a | ids_b)
    stable = total - len(only_a) - len(only_b) - len(changed)

    print(f"Pack A: {len(ids_a)} screens | Pack B: {len(ids_b)} screens")
    print(f"Shared screen ids: {len(shared)}")

    print(f"\nOnly in A (missing on rescan): {len(only_a)}")
    for sid in only_a:
        print(f"  - {sid[:8]}  {screens_a[sid].get('purpose')}")

    print(f"\nOnly in B (new on rescan): {len(only_b)}")
    for sid in only_b:
        print(f"  - {sid[:8]}  {screens_b[sid].get('purpose')}")

    print(f"\nShared but changed content: {len(changed)}")
    for sid in changed:
        print(f"  - {sid[:8]}  {screens_a[sid].get('purpose')}")

    stability_pct = 100 * stable / total if total else 100
    print(f"\nStability: {stable}/{total} screens identical across both runs ({stability_pct:.1f}%).")


if __name__ == "__main__":
    main()

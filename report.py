"""
report.py

The Explorer -> Perceiver -> Synthesizer pipeline produces app_knowledge_pack.json,
which is deliberately machine-facing (compact, meant to be fed to an agent). This
script turns that same pack into a human-readable Markdown report: one section per
screen, listing every recorded element and what it does, plus the reconstructed
journeys and the design rollup.

Nothing here re-derives anything — it only formats what synthesizer.py already
computed, so it stays trivially cheap to re-run.

Usage:
    python report.py --pack-file knowledge_pack/app_knowledge_pack.json \
                      --out-file knowledge_pack/button_report.md
"""

import argparse
import json
from pathlib import Path


def short(h: str, n: int = 8) -> str:
    return h[:n] if h else h


def esc(cell) -> str:
    """Make a value safe to drop into a Markdown table cell."""
    return str(cell if cell is not None else "").replace("|", "\\|").replace("\n", " ")


def render_design(design: dict) -> str:
    lines = ["## Design rollup", ""]

    colors = design.get("colors") or []
    lines.append(
        "**Palette:** " + ", ".join(f"`{c}`" for c in colors)
        if colors else "**Palette:** not enough screenshots to cluster"
    )
    lines.append("")

    components = design.get("components") or []
    if components:
        lines.append("**Recurring component roles:** " + ", ".join(f"`{c}`" for c in components))
        lines.append("")

    tone = design.get("tone_of_voice_samples") or []
    if tone:
        lines.append("**Tone of voice samples:**")
        for t in tone:
            lines.append(f"- {t}")
        lines.append("")

    dark = design.get("supports_dark_mode")
    lines.append(
        f"**Dark mode support:** "
        f"{dark if dark is not None else 'unknown (not inferable from current inputs)'}"
    )
    lines.append("")
    return "\n".join(lines)


def render_journeys(journeys: list, screens_by_id: dict) -> str:
    if not journeys:
        return (
            "## Journeys\n\n"
            "No transitions were recorded (transitions.jsonl was empty or missing), "
            "so no journeys could be reconstructed.\n"
        )

    lines = ["## Journeys", "", "Reconstructed by walking the tap graph from likely entry screens.", ""]
    for j in journeys:
        lines.append(f"### {j['name']}")
        steps = j["steps"]
        via = j.get("via", [])
        start_purpose = screens_by_id.get(steps[0], {}).get("purpose", "unknown purpose")
        lines.append(f"- `{short(steps[0])}` — {start_purpose}")
        for i, label in enumerate(via):
            to = steps[i + 1]
            purpose = screens_by_id.get(to, {}).get("purpose", "unknown purpose")
            lines.append(f"  - tap **{label}** &rarr; `{short(to)}` — {purpose}")
        lines.append("")
    return "\n".join(lines)


def render_screen(screen: dict) -> str:
    lines = [f"### Screen `{short(screen['id'])}` — {screen.get('screen_type') or 'unclassified'}", ""]
    lines.append(f"**Purpose:** {screen.get('purpose') or 'unknown'}  ")
    ref = screen.get("screenshot_ref")
    if ref:
        lines.append(f"**Reference screenshot:** `{ref}`")
    lines.append("")

    elements = screen.get("elements") or []
    if elements:
        lines.append("| Element | Role | What it does |")
        lines.append("|---|---|---|")
        for el in elements:
            action = el.get("action") or "_informational only_"
            lines.append(f"| {esc(el.get('label'))} | {esc(el.get('role'))} | {esc(action)} |")
        lines.append("")
    else:
        lines.append("_No interactive elements were recorded for this screen._")
        lines.append("")

    fields = screen.get("form_fields") or []
    if fields:
        lines.append("**Form fields:**")
        lines.append("")
        lines.append("| Field | Type | Required | Validation hint |")
        lines.append("|---|---|---|---|")
        for f in fields:
            lines.append(
                f"| {esc(f.get('name'))} | {esc(f.get('input_type'))} | "
                f"{esc(f.get('required'))} | {esc(f.get('validation_hint') or '—')} |"
            )
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack-file", default="knowledge_pack/app_knowledge_pack.json")
    parser.add_argument("--out-file", default="knowledge_pack/button_report.md")
    args = parser.parse_args()

    pack_file = Path(args.pack_file)
    if not pack_file.exists():
        raise SystemExit(f"Pack file not found: {pack_file}. Run synthesizer.py first.")

    pack = json.loads(pack_file.read_text())
    screens = pack.get("screens", [])
    journeys = pack.get("journeys", [])
    design = pack.get("design", {})
    screens_by_id = {s["id"]: s for s in screens}

    out = [
        "# App Knowledge Pack — Button & Screen Report",
        "",
        f"Screens explored: **{len(screens)}**  ",
        f"Journeys reconstructed: **{len(journeys)}**",
        "",
        render_design(design),
        render_journeys(journeys, screens_by_id),
        "## Screens",
        "",
    ]
    for screen in screens:
        out.append(render_screen(screen))

    out_file = Path(args.out_file)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text("\n".join(out), encoding="utf-8")
    print(f"Wrote {out_file} ({out_file.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()

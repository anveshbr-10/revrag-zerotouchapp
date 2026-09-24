"""
build_viewer.py

Renders the App Knowledge Pack as a single self-contained HTML "app map" --
each screen's screenshot next to its profile (purpose, type, elements, form
fields), plus the reconstructed journeys and the design rollup up top. This
is the suggested-deliverable viewer from the problem statement:
"Build a viewer showing the app map with each screen's profile next to its
screenshot."

Screenshots are embedded as base64 data URIs so the output is one file you
can open directly or drop into a static host -- it doesn't need the rest of
knowledge_pack/ alongside it (the compact JSON pack stays the machine-facing
artifact; this HTML is the human-facing one).

Usage:
    python build_viewer.py --pack-file knowledge_pack/app_knowledge_pack.json \
                            --out-file knowledge_pack/viewer.html
"""

import argparse
import base64
import html
import json
from pathlib import Path


def embed_image(path_str) -> str:
    if not path_str:
        return ""
    p = Path(path_str)
    if not p.exists():
        return ""
    data = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{data}"


def esc(v) -> str:
    return html.escape(str(v)) if v is not None else ""


def render_elements_table(elements: list) -> str:
    if not elements:
        return "<p class='muted'>No interactive elements recorded.</p>"
    rows = "".join(
        f"<tr><td>{esc(el.get('label'))}</td><td><span class='role'>{esc(el.get('role'))}</span></td>"
        f"<td>{esc(el.get('action') or '—')}</td></tr>"
        for el in elements
    )
    return f"<table><thead><tr><th>Element</th><th>Role</th><th>Action</th></tr></thead><tbody>{rows}</tbody></table>"


def render_fields_table(fields: list) -> str:
    if not fields:
        return ""
    rows = "".join(
        f"<tr><td>{esc(f.get('name'))}</td><td>{esc(f.get('input_type'))}</td>"
        f"<td>{esc(f.get('required'))}</td><td>{esc(f.get('validation_hint') or '—')}</td></tr>"
        for f in fields
    )
    return (
        "<h4>Form fields</h4>"
        f"<table><thead><tr><th>Field</th><th>Type</th><th>Required</th><th>Validation hint</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )


def render_screen_card(screen: dict) -> str:
    img = embed_image(screen.get("screenshot_ref"))
    img_html = f"<img src='{img}' alt='screenshot' />" if img else "<div class='no-shot'>no screenshot</div>"
    return f"""
    <article class="screen-card" id="screen-{esc(screen['id'])}">
      <div class="screen-shot">{img_html}</div>
      <div class="screen-profile">
        <div class="screen-id">#{esc(screen['id'][:8])}</div>
        <span class="badge">{esc(screen.get('screen_type') or 'unclassified')}</span>
        <h3>{esc(screen.get('purpose') or 'Unknown purpose')}</h3>
        {render_elements_table(screen.get('elements', []))}
        {render_fields_table(screen.get('form_fields', []))}
      </div>
    </article>
    """


def render_journeys(journeys: list) -> str:
    if not journeys:
        return "<p class='muted'>No transitions were recorded, so no journeys could be reconstructed.</p>"
    blocks = []
    for j in journeys:
        steps = j["steps"]
        via = j.get("via", [])
        path_html = f"<span class='node'>{esc(steps[0][:8])}</span>"
        for i, label in enumerate(via):
            path_html += (
                f"<span class='edge'>&rarr; {esc(label)} &rarr;</span>"
                f"<span class='node'>{esc(steps[i + 1][:8])}</span>"
            )
        blocks.append(f"<div class='journey'><strong>{esc(j['name'])}</strong><div class='path'>{path_html}</div></div>")
    return "".join(blocks)


def render_design(design: dict) -> str:
    swatches = "".join(
        f"<span class='swatch' style='background:{esc(c)}' title='{esc(c)}'></span>"
        for c in design.get("colors", [])
    )
    tone = "".join(f"<li>{esc(t)}</li>" for t in design.get("tone_of_voice_samples", []))
    components = ", ".join(design.get("components", []) or [])
    fonts = ", ".join(design.get("fonts", []) or [])
    dark = design.get("supports_dark_mode")
    dark_label = "Yes" if dark is True else ("No" if dark is False else "Unknown (single-pass scan)")
    return f"""
    <section class="design">
      <h2>Design rollup</h2>
      <div class="swatches">{swatches or '<span class="muted">no palette extracted</span>'}</div>
      <p><strong>Recurring components:</strong> {esc(components) or '—'}</p>
      <p><strong>Font sizes observed:</strong> {esc(fonts) or '—'}</p>
      <p><strong>Dark mode support:</strong> {dark_label}</p>
      {'<h4>Tone of voice</h4><ul>' + tone + '</ul>' if tone else ''}
    </section>
    """


PAGE_TEMPLATE = """<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<title>App Knowledge Pack Viewer</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 0; padding: 24px; background: #0f1115; color: #e8e8ec; }}
  h1 {{ font-size: 1.4rem; margin-bottom: 4px; }}
  .subtitle {{ color: #9a9aa5; margin-top: 0; }}
  section.design {{ background: #181b22; border-radius: 12px; padding: 16px 20px; margin-bottom: 24px; }}
  .swatches {{ display: flex; gap: 6px; margin: 8px 0; }}
  .swatch {{ width: 28px; height: 28px; border-radius: 6px; border: 1px solid #333; }}
  .journeys {{ margin-bottom: 28px; }}
  .journey {{ background: #181b22; border-radius: 10px; padding: 10px 14px; margin-bottom: 8px; }}
  .path {{ display: flex; flex-wrap: wrap; align-items: center; gap: 4px; margin-top: 6px; font-size: 0.85rem; }}
  .node {{ background: #2a2f3a; padding: 2px 8px; border-radius: 6px; font-family: monospace; }}
  .edge {{ color: #9a9aa5; font-size: 0.8rem; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 18px; }}
  .screen-card {{ background: #181b22; border-radius: 12px; overflow: hidden; display: flex; flex-direction: column; }}
  .screen-shot {{ background: #000; display: flex; align-items: center; justify-content: center; max-height: 420px; overflow: hidden; }}
  .screen-shot img {{ width: 100%; object-fit: contain; max-height: 420px; }}
  .no-shot {{ padding: 60px 0; color: #666; text-align: center; width: 100%; }}
  .screen-profile {{ padding: 14px 16px; }}
  .screen-id {{ font-family: monospace; font-size: 0.75rem; color: #767684; }}
  .badge {{ display: inline-block; background: #2a2f3a; color: #b9c2ff; font-size: 0.7rem; padding: 2px 8px; border-radius: 20px; margin: 4px 0; }}
  h3 {{ margin: 6px 0 10px; font-size: 1.05rem; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.82rem; margin-bottom: 10px; }}
  th, td {{ text-align: left; padding: 4px 6px; border-bottom: 1px solid #2a2f3a; vertical-align: top; }}
  th {{ color: #9a9aa5; font-weight: 600; }}
  .role {{ background: #23283a; padding: 1px 6px; border-radius: 6px; font-size: 0.72rem; }}
  .muted {{ color: #767684; font-style: italic; }}
</style>
</head>
<body>
  <h1>App Knowledge Pack</h1>
  <p class="subtitle">{screen_count} screens &middot; {journey_count} journeys</p>

  {design_html}

  <section class="journeys">
    <h2>Journeys</h2>
    {journeys_html}
  </section>

  <section class="grid">
    {screen_cards_html}
  </section>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack-file", default="knowledge_pack/app_knowledge_pack.json")
    parser.add_argument("--out-file", default="knowledge_pack/viewer.html")
    args = parser.parse_args()

    pack_file = Path(args.pack_file)
    if not pack_file.exists():
        raise SystemExit(f"Pack file not found: {pack_file}. Run synthesizer.py first.")

    pack = json.loads(pack_file.read_text())
    screens = pack.get("screens", [])
    journeys = pack.get("journeys", [])
    design = pack.get("design", {})

    page = PAGE_TEMPLATE.format(
        screen_count=len(screens),
        journey_count=len(journeys),
        design_html=render_design(design),
        journeys_html=render_journeys(journeys),
        screen_cards_html="".join(render_screen_card(s) for s in screens),
    )

    out_file = Path(args.out_file)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(page, encoding="utf-8")
    print(f"Wrote {out_file} ({out_file.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()

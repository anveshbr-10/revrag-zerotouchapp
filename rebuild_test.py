"""
rebuild_test.py

The problem statement asks for: "a rebuild test recreating 2-3 screens from
the knowledge pack alone." This script picks N screens from
app_knowledge_pack.json, keeps only purpose/screen_type/elements/form_fields
(never touching screenshot_ref while building the mock), and renders each
element as a plain HTML control matching its recorded role
(button/text_field/checkbox/etc). The real screenshot is placed alongside the
reconstruction only afterwards, purely so a human can judge whether the pack
captured enough to rebuild the screen.

Usage:
    python rebuild_test.py --pack-file knowledge_pack/app_knowledge_pack.json \
                            --out-file knowledge_pack/rebuild_test.html \
                            --count 3
"""

import argparse
import base64
import html
import json
import random
from pathlib import Path


def esc(v) -> str:
    return html.escape(str(v)) if v is not None else ""


def embed_image(path_str):
    if not path_str:
        return None
    p = Path(path_str)
    if not p.exists():
        return None
    return f"data:image/png;base64,{base64.b64encode(p.read_bytes()).decode('ascii')}"


ROLE_RENDERERS = {
    "button": lambda label: f"<button class='mock-btn'>{esc(label)}</button>",
    "text_field": lambda label: f"<label class='mock-field'>{esc(label)}<input type='text' placeholder='{esc(label)}' /></label>",
    "checkbox": lambda label: f"<label class='mock-check'><input type='checkbox'/> {esc(label)}</label>",
    "toggle": lambda label: f"<label class='mock-toggle'>{esc(label)} <span class='switch'></span></label>",
    "dropdown": lambda label: f"<label class='mock-field'>{esc(label)}<select><option>{esc(label)}</option></select></label>",
    "tab": lambda label: f"<span class='mock-tab'>{esc(label)}</span>",
    "link": lambda label: f"<a class='mock-link' href='#'>{esc(label)}</a>",
    "image": lambda label: f"<div class='mock-image'>{esc(label)}</div>",
    "static_text": lambda label: f"<p class='mock-text'>{esc(label)}</p>",
}


def render_mock_element(el: dict) -> str:
    renderer = ROLE_RENDERERS.get(el.get("role"), lambda label: f"<div class='mock-other'>{esc(label)}</div>")
    return renderer(el.get("label") or "")


def render_mock_screen(screen: dict) -> str:
    elements_html = "\n".join(render_mock_element(el) for el in screen.get("elements", []))
    fields_html = "\n".join(
        f"<label class='mock-field'>{esc(f.get('name'))}"
        f"<input type='{esc(f.get('input_type') or 'text')}' placeholder='{esc(f.get('name'))}' /></label>"
        for f in screen.get("form_fields", [])
    )
    return f"<div class='mock-screen'>{elements_html}{fields_html}</div>"


def render_pair(screen: dict) -> str:
    real = embed_image(screen.get("screenshot_ref"))
    real_html = f"<img src='{real}' />" if real else "<div class='no-shot'>no screenshot on file</div>"
    return f"""
    <section class="pair">
      <h2>Screen {esc(screen['id'][:8])} &mdash; {esc(screen.get('purpose') or 'unknown purpose')}</h2>
      <div class="cols">
        <div class="col"><h3>Real screenshot</h3>{real_html}</div>
        <div class="col"><h3>Reconstructed from knowledge pack alone</h3>{render_mock_screen(screen)}</div>
      </div>
    </section>
    """


PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Rebuild test</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; background: #0f1115; color: #e8e8ec; padding: 24px; }}
  h1 {{ font-size: 1.3rem; }}
  p.note {{ color: #9a9aa5; max-width: 680px; }}
  .pair {{ background: #181b22; border-radius: 12px; padding: 16px 20px; margin-bottom: 24px; }}
  .cols {{ display: flex; gap: 20px; flex-wrap: wrap; }}
  .col {{ flex: 1; min-width: 280px; }}
  .col img {{ max-width: 100%; border-radius: 8px; border: 1px solid #2a2f3a; }}
  .no-shot {{ color: #767684; font-style: italic; }}
  .mock-screen {{ background: #fff; color: #111; border-radius: 8px; padding: 16px; display: flex; flex-direction: column; gap: 10px; min-height: 200px; }}
  .mock-btn {{ background: #2f6fed; color: #fff; border: none; padding: 8px 14px; border-radius: 6px; align-self: flex-start; }}
  .mock-field input, .mock-field select {{ display: block; width: 100%; padding: 6px 8px; margin-top: 4px; border: 1px solid #ccc; border-radius: 6px; }}
  .mock-link {{ color: #2f6fed; }}
  .mock-tab {{ display: inline-block; padding: 4px 10px; background: #eee; border-radius: 6px; margin-right: 6px; }}
  .mock-image {{ background: #eee; padding: 30px; text-align: center; border-radius: 6px; color: #888; }}
  .switch {{ display: inline-block; width: 34px; height: 18px; background: #ccc; border-radius: 10px; vertical-align: middle; margin-left: 6px; }}
</style>
</head>
<body>
  <h1>Rebuild test &mdash; {count} screen(s)</h1>
  <p class="note">Each reconstruction below was generated from the knowledge pack's
  <code>elements</code>/<code>form_fields</code>/<code>purpose</code> only &mdash; the
  screenshot was never consulted while building it. It's placed next to the real
  screenshot purely so a human can judge whether the pack captured enough to
  recreate the screen.</p>
  {pairs}
</body></html>
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack-file", default="knowledge_pack/app_knowledge_pack.json")
    parser.add_argument("--out-file", default="knowledge_pack/rebuild_test.html")
    parser.add_argument("--count", type=int, default=3)
    parser.add_argument("--seed", type=int, default=0, help="for reproducible screen selection")
    args = parser.parse_args()

    pack_file = Path(args.pack_file)
    if not pack_file.exists():
        raise SystemExit(f"Pack file not found: {pack_file}. Run synthesizer.py first.")

    pack = json.loads(pack_file.read_text())
    screens = pack.get("screens", [])
    if not screens:
        raise SystemExit("No screens in pack.")

    random.seed(args.seed)
    chosen = random.sample(screens, min(args.count, len(screens)))

    page = PAGE.format(
        count=len(chosen),
        pairs="\n".join(render_pair(s) for s in chosen),
    )

    out_file = Path(args.out_file)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(page, encoding="utf-8")
    print(f"Wrote {out_file} with {len(chosen)} screen(s).")


if __name__ == "__main__":
    main()

"""
perceiver.py  — Gemini Vision edition
Replaces the Ollama call with Google Gemini 1.5 Flash (free tier, vision-capable).
Everything else (idempotent re-run, same output schema) stays identical.

Setup:
    pip install google-generativeai
    export GEMINI_API_KEY="your_key_here"

Usage:
    python3 perceiver.py --raw-dir knowledge_pack/raw --out-dir knowledge_pack/perceived
"""

import argparse
import base64
import json
import os
import re
import sys
from pathlib import Path

import google.generativeai as genai

GEMINI_MODEL = "gemini-3.6-flash"

genai.configure(api_key=os.environ["GEMINI_API_KEY"])

SYSTEM_PROMPT = """You are analyzing a single screen of an unfamiliar Android app to build a
structured knowledge pack for an AI agent that will later act on this app on
a user's behalf. You are given a screenshot and a trimmed accessibility tree.

Rules:
- Base every claim on what is visible in the screenshot or present in the tree.
  Do not invent elements, labels, or behavior that isn't evidenced.
- Ignore raw resource-id strings and android class names as user-facing labels —
  describe elements the way a person looking at the screen would.
- If a field cannot be determined, use null rather than guessing.
- Respond with ONLY valid JSON matching the schema below. No prose, no markdown
  fences, no commentary before or after.

Return JSON with exactly this shape:
{
  "purpose": "<one plain-language sentence: what is this screen for>",
  "screen_type": "<one of: login, form, list, detail, dashboard, confirmation, error, onboarding, settings, other>",
  "elements": [
    {
      "label": "<visible text or plain description if no text>",
      "role": "<one of: button, text_field, checkbox, toggle, dropdown, tab, link, image, static_text, other>",
      "action": "<what happens on interaction, or null if purely informational>"
    }
  ],
  "form_fields": [
    {
      "name": "<inferred field name>",
      "input_type": "<text, email, password, number, date, otp, other>",
      "required": true,
      "validation_hint": "<any visible hint/error text, else null>"
    }
  ],
  "tone_of_voice_sample": "<any 1-2 short copy snippets visible on screen, verbatim, else null>"
}"""


def trim_tree(tree_xml: str) -> str:
    nodes = re.findall(r"<node[^>]*/?>", tree_xml)
    kept = []
    for node in nodes:
        has_id = 'resource-id=""' not in node
        has_text = 'text=""' not in node
        is_clickable = 'clickable="true"' in node
        if has_id or has_text or is_clickable:
            kept.append(node.strip())
    return "\n".join(kept)


def find_screenshot(screen_dir: Path) -> Path | None:
    shots = sorted(screen_dir.glob("screenshot_*.png"))
    return shots[0] if shots else None


def call_gemini(image_path: Path, trimmed_tree: str) -> dict:
    model = genai.GenerativeModel(GEMINI_MODEL)

    with open(image_path, "rb") as f:
        image_data = f.read()

    image_part = {
        "mime_type": "image/png",
        "data": base64.b64encode(image_data).decode("utf-8")
    }

    prompt = (
        SYSTEM_PROMPT
        + f"\n\nACCESSIBILITY TREE (trimmed):\n{trimmed_tree}\n\nReturn the JSON now."
    )

    response = model.generate_content([
        {"mime_type": "image/png", "data": base64.b64encode(image_data).decode("utf-8")},
        prompt
    ])

    raw = response.text.strip()
    # Strip markdown fences if model adds them
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw.strip())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", default="knowledge_pack/raw")
    parser.add_argument("--out-dir", default="knowledge_pack/perceived")
    args = parser.parse_args()

    raw_dir = Path(args.raw_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not raw_dir.exists():
        print(f"Raw dir not found: {raw_dir}", file=sys.stderr)
        sys.exit(1)

    screen_dirs = [d for d in raw_dir.iterdir() if d.is_dir()]
    print(f"Found {len(screen_dirs)} unique screens.")

    processed, skipped, failed = 0, 0, 0

    for screen_dir in screen_dirs:
        screen_hash = screen_dir.name
        out_file = out_dir / f"{screen_hash}.json"

        if out_file.exists():
            skipped += 1
            continue

        tree_file = screen_dir / "tree.xml"
        screenshot = find_screenshot(screen_dir)

        if not tree_file.exists() or screenshot is None:
            print(f"  [skip] {screen_hash}: missing tree.xml or screenshot")
            failed += 1
            continue

        trimmed = trim_tree(tree_file.read_text())

        try:
            result = call_gemini(screenshot, trimmed)
        except Exception as e:
            if "429" in str(e):
                print(f"  [rate limit] {screen_hash}: waiting 60s...")
                import time
                time.sleep(60)
                try:
                    result = call_gemini(screenshot, trimmed)
                except Exception as e2:
                    print(f"  [fail] {screen_hash}: {e2}")
                    failed += 1
                    continue
            else:
                print(f"  [fail] {screen_hash}: {e}")
                failed += 1
                continue

        result["_screen_hash"] = screen_hash
        result["_screenshot_ref"] = str(screenshot)

        out_file.write_text(json.dumps(result, indent=2))
        processed += 1
        print(f"  [ok] {screen_hash} -> {out_file.name}")

    print(f"\nDone. processed={processed} skipped={skipped} failed={failed}")


if __name__ == "__main__":
    main()
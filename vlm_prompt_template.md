# Perceiver — VLM Prompt Template

Used once per captured screen (screenshot + trimmed accessibility tree in → structured
JSON out). Keep the tree trimmed before sending — it's usually 80% noise (layout
containers with no text/id) that just burns context and confuses the model.

## Step 0 — Trim the tree (do this in code, not in the prompt)

Keep only nodes where at least one of these is true: `clickable=true`,
`text` is non-empty, or `resource-id` is non-empty. Drop pure layout containers.
This alone usually cuts tree size by 5–10x and is a big part of staying under the
"raw trees exceed 1.5MB" constraint.

## System prompt

```
You are analyzing a single screen of an unfamiliar Android app to build a
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
```

## User prompt (fill placeholders per screen)

```
SCREENSHOT: [attached image]

ACCESSIBILITY TREE (trimmed):
{{trimmed_tree_json_or_xml}}

SCREEN CONTEXT:
- Previous screen purpose (if known): {{previous_screen_purpose}}
- Action that led here (if known): {{triggering_action}}

Return JSON with exactly this shape:

{
  "purpose": "<one plain-language sentence: what is this screen for>",
  "screen_type": "<one of: login, form, list, detail, dashboard, confirmation, error, onboarding, settings, other>",
  "elements": [
    {
      "label": "<visible text or plain description if no text, e.g. 'search icon top-right'>",
      "role": "<one of: button, text_field, checkbox, toggle, dropdown, tab, link, image, static_text, other>",
      "action": "<what happens on interaction, e.g. 'navigates to checkout' or 'submits form' — null if purely informational>"
    }
  ],
  "form_fields": [
    {
      "name": "<inferred field name, e.g. 'email'>",
      "input_type": "<text, email, password, number, date, otp, other>",
      "required": <true/false/null if unknown>,
      "validation_hint": "<any visible hint/error text, else null>"
    }
  ],
  "tone_of_voice_sample": "<any 1-2 short copy snippets visible on screen, verbatim, for later brand-tone rollup — null if no copy>"
}
```

## Example output (for calibration — don't send this to the model)

```json
{
  "purpose": "Collects the user's email and password to sign in to their account.",
  "screen_type": "login",
  "elements": [
    {"label": "Email input field", "role": "text_field", "action": null},
    {"label": "Password input field", "role": "text_field", "action": null},
    {"label": "Sign In button", "role": "button", "action": "submits credentials and navigates to home"},
    {"label": "Forgot password?", "role": "link", "action": "navigates to password reset flow"}
  ],
  "form_fields": [
    {"name": "email", "input_type": "email", "required": true, "validation_hint": null},
    {"name": "password", "input_type": "password", "required": true, "validation_hint": "Must be at least 8 characters"}
  ],
  "tone_of_voice_sample": "Welcome back!"
}
```

## Notes on use

- Call this once per **unique screen hash**, not per visit — the Explorer already
  dedupes, so you shouldn't be re-spending VLM calls on repeat states.
- For the design/brand rollup pass, run a **separate** prompt across all
  `tone_of_voice_sample` strings and a sampled set of screenshots — asking one
  prompt to do both per-screen extraction and cross-app brand synthesis in a
  single call tends to produce weaker results on both.
- If you swap to an on-device model later, keep this exact schema — only the
  system prompt's strictness may need loosening for a smaller model (e.g. add
  one worked example directly in the system prompt if the model drifts from
  the JSON shape).

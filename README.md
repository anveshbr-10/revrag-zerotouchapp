# Zero-Touch App Understanding

This project automates Android app exploration and converts each unique screen into a structured knowledge pack that can be consumed later by an agent or reviewed by a human.

The current repo state reflects a working pipeline that:

- explores the foreground Android app with UiAutomator,
- captures screenshots and accessibility-tree XML for each unique screen,
- asks a vision model to describe the screen in structured JSON,
- merges screens plus tap/back transitions into a compact `app_knowledge_pack.json`,
- renders a human-friendly report, viewer, and rebuild comparison.

The project has already been used on a sample app in this workspace, and the generated artifacts are present under `knowledge_pack/`.

## What is in this repo

```text
android/                  Android test host and UiAutomator explorer
perceiver.py              Screen-by-screen perception via Gemini
synthesizer.py            Merges raw screens + transitions into a single pack
report.py                 Human-readable markdown report
build_viewer.py           Single-file HTML app map
rebuild_test.py           Reconstructs a few screens from the pack alone
compare_packs.py          Stability diff between two pack runs
dark_mode_check.py        Merge light/dark pass into design.supports_dark_mode
run_pipeline.sh           End-to-end single-pass script
requirements.txt          Python dependencies
knowledge_pack/           Generated pack artifacts and sample data
```

## Current implementation details

### 1) Android exploration

`android/explorer/src/androidTest/java/com/revrag/explorer/AppExplorer.kt` is the on-device explorer.

What it does today:

- launches the target app package,
- captures the current accessibility tree and computes a structural hash for each screen,
- saves a screenshot and `tree.xml` for each unique screen,
- fills likely login / OTP / KYC text fields with test values inferred from hints,
- tries the next unvisited clickable element,
- scrolls down once if nothing new is left to tap,
- records taps and back actions in `transitions.jsonl`.

Important current repo detail: the explorer is hardcoded to target the package `org.wikipedia.alpha` in the current sample run. If you want to scan another app, update that value in `AppExplorer.kt` before running the instrumentation test.

The raw output is written under the device cache path, for example:

```text
knowledge_pack/raw/<screen_hash>/tree.xml
knowledge_pack/raw/<screen_hash>/screenshot_<step>.png
knowledge_pack/raw/transitions.jsonl
```

The same explorer supports a second mode for dark-mode exploration by using an instrumentation argument such as `raw_subdir=light` or `raw_subdir=dark` so the two runs do not overwrite each other.

### 2) Perception step

`perceiver.py` currently uses Google Gemini, not Ollama.

Current configuration in the file:

- `GEMINI_MODEL = "gemini-3.6-flash"`
- authentication via `GEMINI_API_KEY`
- the script reads each screenshot + trimmed XML tree and asks the model for structured output with schema fields like:
  - `purpose`
  - `screen_type`
  - `elements[]`
  - `form_fields[]`
  - `tone_of_voice_sample`

This is idempotent: screens already processed are skipped on re-run.

### 3) Synthesis step

`synthesizer.py` combines the outputs from `perceiver.py` and the transition log from the explorer.

It creates a compact JSON pack shaped like:

```json
{
  "screens": [ ... ],
  "journeys": [ ... ],
  "design": {
    "colors": [ ... ],
    "fonts": [ ... ],
    "components": [ ... ],
    "tone_of_voice_samples": [ ... ],
    "supports_dark_mode": null
  }
}
```

The script reconstructs forward paths from likely entry screens using the raw tap graph and summarizes a basic design palette from screenshots.

### 4) Human-facing outputs

The repo includes several post-processing scripts:

- `report.py` creates a readable Markdown report with one section per screen plus journeys and design summary.
- `build_viewer.py` builds a single self-contained HTML viewer with screenshots and payload details.
- `rebuild_test.py` rebuilds a few screens from the knowledge pack alone and shows them next to the real screenshot.

These are designed to make the machine-generated pack easier to inspect and validate.

## Generated sample artifacts in this workspace

The repo already contains a working sample output under `knowledge_pack/`:

```text
knowledge_pack/
  app_knowledge_pack.json
  button_report.md
  viewer.html
  rebuild_test.html
  raw/
  perceived/
```

This sample reflects a real scan of the Wikipedia app in this workspace and is useful as a baseline when adapting the project to another target app.

## Setup

### Python

```bash
pip install -r requirements.txt
```

The current requirements pin the packages actually used by the scripts:

- `requests`
- `pillow`
- `scikit-learn`
- `numpy`
- `google-generativeai`

Set your API key before running the perceiver:

```bash
export GEMINI_API_KEY="your_key_here"
```

### Android

Open the Android project in `android/` and let Gradle sync:

```bash
cd android
./gradlew connectedAndroidTest
```

Before doing that, manually launch the target app so it is in the foreground. The explorer interacts with the app that is already running; it does not launch a target app by itself.

For Android storage issues, keep in mind the project uses `/sdcard/knowledge_pack`-style output and expects the device/emulator to allow the write path. In practice, emulator-based runs are often easier than newer OEM storage-restricted devices.

## Run the pipeline

From the repo root:

```bash
./run_pipeline.sh
```

or with a specific device serial:

```bash
./run_pipeline.sh emulator-5554
```

The script performs the standard flow:

```bash
adb pull /sdcard/knowledge_pack/raw knowledge_pack/raw
python3 perceiver.py --raw-dir knowledge_pack/raw --out-dir knowledge_pack/perceived
python3 synthesizer.py --perceived-dir knowledge_pack/perceived --raw-dir knowledge_pack/raw --out-file knowledge_pack/app_knowledge_pack.json
python3 report.py --pack-file knowledge_pack/app_knowledge_pack.json --out-file knowledge_pack/button_report.md
python3 build_viewer.py --pack-file knowledge_pack/app_knowledge_pack.json --out-file knowledge_pack/viewer.html
python3 rebuild_test.py --pack-file knowledge_pack/app_knowledge_pack.json --out-file knowledge_pack/rebuild_test.html --count 3
```

## Optional extra analysis passes

### Stability check

To compare two scans of the same app:

```bash
python3 compare_packs.py \
  --pack-a knowledge_pack/run1/app_knowledge_pack.json \
  --pack-b knowledge_pack/run2/app_knowledge_pack.json
```

This reports shared screen ids, newly missing screens, changed screens, and a stability percentage.

### Dark mode check

This is a separate pass requiring a light-mode and dark-mode run of the app explorer. The repo has a dedicated helper for it:

```bash
adb shell cmd uimode night no
cd android && ./gradlew connectedAndroidTest -Pandroid.testInstrumentationRunnerArguments.raw_subdir=light
adb pull /sdcard/knowledge_pack/raw_light knowledge_pack/raw_light
python3 perceiver.py --raw-dir knowledge_pack/raw_light --out-dir knowledge_pack/perceived_light
python3 synthesizer.py --perceived-dir knowledge_pack/perceived_light --raw-dir knowledge_pack/raw_light --out-file knowledge_pack/app_knowledge_pack_light.json

adb shell cmd uimode night yes
cd android && ./gradlew connectedAndroidTest -Pandroid.testInstrumentationRunnerArguments.raw_subdir=dark
adb pull /sdcard/knowledge_pack/raw_dark knowledge_pack/raw_dark
python3 perceiver.py --raw-dir knowledge_pack/raw_dark --out-dir knowledge_pack/perceived_dark
python3 synthesizer.py --perceived-dir knowledge_pack/perceived_dark --raw-dir knowledge_pack/raw_dark --out-file knowledge_pack/app_knowledge_pack_dark.json

python3 dark_mode_check.py \
  --light-pack knowledge_pack/app_knowledge_pack_light.json \
  --dark-pack knowledge_pack/app_knowledge_pack_dark.json \
  --out-file knowledge_pack/app_knowledge_pack.json
```

This writes `design.supports_dark_mode` and keeps the dark palette in `design.colors_dark`.

## Output summary

- `knowledge_pack/app_knowledge_pack.json` — machine-facing bundle of screens, journeys, and design metadata.
- `knowledge_pack/button_report.md` — human-readable screen-by-screen report.
- `knowledge_pack/viewer.html` — single-file map of the app.
- `knowledge_pack/rebuild_test.html` — reconstruction check using only the pack data.

## Known limitations

- The explorer is intentionally simple and uses a first-found path approach for journey reconstruction; it does not exhaustively traverse the full state graph.
- The design palette is a best-effort summary from a sampled subset of screenshots, not a full-color audit.
- Forms are filled using a short heuristic hint map; weird custom fields can still be missed.
- `perceiver.py` trusts the vision model output format and will fail or degrade if the model is inconsistent.
- Dark-mode support is inferred via a light-vs-dark palette heuristic, not by reading Android's `UI_MODE_NIGHT` state inside the app itself.

## Practical usage

This repo is best used as a full-stack app exploration system:

1. point the Android explorer at the target app package,
2. run the instrumented explorer on a device or emulator,
3. collect the raw dump,
4. run the perceiver and synthesizer,
5. inspect the report or viewer,
6. refine field hints and target package as needed for the next app.

The generated pack is intentionally compact and designed to be handed to an agent that later acts on the app or validates the discovered flow.

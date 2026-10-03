# Zero-Touch App Understanding

An AI-powered pipeline that autonomously explores any Android app and produces a structured, compact App Knowledge Pack — covering every screen, its UI elements, navigation journeys, and brand design language — without any human recording flows by hand.

---

## What this does

- Autonomously explores a foreground Android app using UiAutomator (taps, scrolls, fills forms, backs out)
- Captures screenshots and accessibility-tree XML for every unique screen it discovers
- Sends each screen to a Gemini vision model to produce structured JSON describing its purpose, elements, form fields, and tone
- Merges all screens plus tap/back transitions into a compact `app_knowledge_pack.json`
- Renders a human-friendly HTML viewer, a screen-by-screen markdown report, and a rebuild comparison test

---

## Repo structure

```text
android/                  Android instrumented test — the autonomous explorer
perceiver.py              Screen-by-screen perception via Gemini Vision
synthesizer.py            Merges raw screens + transitions into one pack
report.py                 Human-readable markdown report generator
build_viewer.py           Builds a single-file HTML app map viewer
rebuild_test.py           Reconstructs screens from the pack and compares to real screenshots
compare_packs.py          Stability diff between two pack runs
dark_mode_check.py        Merges light/dark passes into design.supports_dark_mode
run_pipeline.sh           End-to-end pipeline script (Linux/Mac)
requirements.txt          Python dependencies
knowledge_pack/           Generated output artifacts
```

---

## How it works

### 1. Android Explorer

`android/explorer/src/androidTest/java/com/revrag/explorer/AppExplorer.kt`

The explorer runs as an Android instrumented test using UiAutomator. At each step it:

1. Dumps the accessibility tree of the current screen
2. Computes a structural hash (ignores pixel coordinates so the same screen always hashes the same)
3. Takes a screenshot and saves tree.xml for each unique screen
4. Fills login/OTP/KYC fields with test values inferred from field hints
5. Taps the next unvisited clickable element
6. Scrolls down once if nothing new is left to tap
7. Backs out if all elements on the screen have been tried
8. Saves every tap and back action to `transitions.jsonl` for journey reconstruction

Screenshots are saved to `/sdcard/knowledge_pack_screenshots/` for easy pulling via ADB.

### 2. Perception

`perceiver.py` sends each screenshot plus its trimmed accessibility tree to Gemini and gets back structured JSON with:

- `purpose` — what the screen is for in plain language
- `screen_type` — login, list, detail, dashboard, form, etc.
- `elements[]` — every visible element with label, role, and action
- `form_fields[]` — input fields with type and validation hints
- `tone_of_voice_sample` — copy snippets visible on screen

This step is idempotent — already processed screens are skipped on re-run.

### 3. Synthesis

`synthesizer.py` combines perceiver output and the transition log into a single compact pack:

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

### 4. Human-facing outputs

- `report.py` — markdown report with one section per screen plus journeys and design summary
- `build_viewer.py` — self-contained HTML viewer with screenshots and screen profiles side by side
- `rebuild_test.py` — reconstructs screens from the pack alone and shows them next to the real screenshot

---

## Running from scratch

### Prerequisites

- Windows, Mac, or Linux laptop
- Python 3.10 or higher
- Android Studio installed (for Gradle and SDK)
- ADB (Android Debug Bridge) installed
- A physical Android phone or emulator with USB debugging enabled
- A Google Gemini API key (free tier at https://aistudio.google.com/app/apikey)
- The target app installed on your phone

### Step 1 — Clone and install Python dependencies

```bash
cd appknowledge
pip install -r requirements.txt
pip install google-generativeai
```

### Step 2 — Enable USB debugging on your phone

1. Go to Settings → About Phone
2. Tap Build Number 7 times — you are now a developer
3. Go back → Developer Options → enable USB Debugging
4. Also enable Stay Awake so the screen does not turn off during exploration
5. Connect phone to laptop via USB and tap Allow on the popup

Verify your phone is visible:

```bash
adb devices
```

You should see your device serial number listed.

### Step 3 — Install the target app

Download and install any APK on your phone. For example Wikipedia Alpha:

```
https://github.com/wikimedia/apps-android-wikipedia/releases
```

```bash
adb install app-release.apk
```

Or use any app already installed on your phone.

### Step 4 — Set your target app package in AppExplorer.kt

Open:

```
android/explorer/src/androidTest/java/com/revrag/explorer/AppExplorer.kt
```

Find:

```kotlin
private val targetPackage: String = "org.wikipedia.alpha"
```

Change `org.wikipedia.alpha` to the package name of your target app.

To find any app's package name:

```bash
adb shell pm list packages | grep <appname>
```

### Step 5 — Build and install the explorer APKs

```bash
cd android
./gradlew assembleDebug assembleAndroidTest --no-daemon
adb install -r explorer/build/outputs/apk/debug/explorer-debug.apk
adb install -r explorer/build/outputs/apk/androidTest/debug/explorer-debug-androidTest.apk
```

On Windows PowerShell use `.\gradlew.bat` instead of `./gradlew`.

### Step 6 — Create the output folder on device and run the explorer

```bash
adb shell mkdir -p /sdcard/knowledge_pack_screenshots
```

Open the target app on your phone and leave it in the foreground. Then run:

```bash
adb shell am instrument -w -r com.revrag.explorer.test/androidx.test.runner.AndroidJUnitRunner
```

The explorer will run for several minutes tapping through the app automatically. It stops on its own when done or after hitting the step limit.

### Step 7 — Pull the captured data

```bash
mkdir -p knowledge_pack/raw
mkdir -p knowledge_pack/screenshots

adb pull /sdcard/knowledge_pack_screenshots knowledge_pack/screenshots
```

List what screens were captured:

```bash
adb shell run-as com.revrag.explorer ls cache/knowledge_pack/raw
```

For each hash folder shown, pull the tree.xml:

```bash
mkdir knowledge_pack/raw/<hash>
adb shell run-as com.revrag.explorer cat cache/knowledge_pack/raw/<hash>/tree.xml > knowledge_pack/raw/<hash>/tree.xml
```

Pull transitions:

```bash
adb shell run-as com.revrag.explorer cat cache/knowledge_pack/raw/transitions.jsonl > knowledge_pack/raw/transitions.jsonl
```

Copy screenshots into matching raw folders.

On Linux/Mac:

```bash
for file in knowledge_pack/screenshots/knowledge_pack_screenshots/*.png; do
    hash=$(basename "$file" .png)
    if [ -d "knowledge_pack/raw/$hash" ]; then
        cp "$file" "knowledge_pack/raw/$hash/screenshot_1.png"
    fi
done
```

On Windows PowerShell:

```powershell
$files = Get-ChildItem "knowledge_pack\screenshots\knowledge_pack_screenshots\*.png"
foreach ($file in $files) {
    $hash = $file.BaseName
    $dest = "knowledge_pack\raw\$hash"
    if (Test-Path $dest) {
        Copy-Item $file.FullName "$dest\screenshot_1.png" -Force
    }
}
```

### Step 8 — Set your Gemini API key

On Linux/Mac:

```bash
export GEMINI_API_KEY="your_key_here"
```

On Windows PowerShell:

```powershell
$env:GEMINI_API_KEY = "your_key_here"
```

Get a free key from: https://aistudio.google.com/app/apikey

Note: the free tier allows 20 requests per day per account. For large apps with many screens, use multiple Google accounts and switch keys when one hits the limit. The perceiver is idempotent — it skips already processed screens so you can switch keys and rerun safely.

### Step 9 — Run the full pipeline

```bash
python perceiver.py --raw-dir knowledge_pack/raw --out-dir knowledge_pack/perceived
python synthesizer.py --perceived-dir knowledge_pack/perceived --raw-dir knowledge_pack/raw --out-file knowledge_pack/app_knowledge_pack.json
python report.py --pack-file knowledge_pack/app_knowledge_pack.json --out-file knowledge_pack/button_report.md
python build_viewer.py --pack-file knowledge_pack/app_knowledge_pack.json --out-file knowledge_pack/viewer.html
python rebuild_test.py --pack-file knowledge_pack/app_knowledge_pack.json --out-file knowledge_pack/rebuild_test.html --count 3
```

### Step 10 — View your outputs

Open these files in your browser:

- `knowledge_pack/viewer.html` — full app map with screenshots and screen profiles
- `knowledge_pack/rebuild_test.html` — rebuild comparison showing real screenshot vs pack reconstruction
- `knowledge_pack/button_report.md` — human readable report
- `knowledge_pack/app_knowledge_pack.json` — machine readable structured knowledge pack

---

## Optional passes

### Stability check

Run the explorer twice saving into separate folders then compare:

```bash
python compare_packs.py \
  --pack-a knowledge_pack/run1/app_knowledge_pack.json \
  --pack-b knowledge_pack/run2/app_knowledge_pack.json
```

Reports shared screens, missing screens, changed screens, and a stability percentage.

### Dark mode check

Run the explorer in light mode and dark mode separately:

```bash
adb shell cmd uimode night no
adb shell am instrument -w -r -e raw_subdir light com.revrag.explorer.test/androidx.test.runner.AndroidJUnitRunner

adb shell cmd uimode night yes
adb shell am instrument -w -r -e raw_subdir dark com.revrag.explorer.test/androidx.test.runner.AndroidJUnitRunner
```

Then run perceiver and synthesizer on each and merge:

```bash
python dark_mode_check.py \
  --light-pack knowledge_pack/app_knowledge_pack_light.json \
  --dark-pack knowledge_pack/app_knowledge_pack_dark.json \
  --out-file knowledge_pack/app_knowledge_pack.json
```

---

## Outputs

| File | Description |
|---|---|
| `knowledge_pack/app_knowledge_pack.json` | Machine-readable bundle of all screens, journeys, and design metadata |
| `knowledge_pack/button_report.md` | Human-readable screen-by-screen report |
| `knowledge_pack/viewer.html` | Visual app map with screenshots and element profiles |
| `knowledge_pack/rebuild_test.html` | Side-by-side reconstruction test |

---

## Known limitations

- The explorer uses a first-found DFS approach and may not discover every screen in very large apps within the step budget
- Design palette is a best-effort summary from a sampled subset of screenshots
- Forms are filled using a short heuristic hint map — custom OTP or unusual field names may be missed
- Gemini free tier is limited to 20 requests per day per account — use multiple accounts for large apps
- On newer Android phones (Android 13+) writing directly to sdcard from test APKs requires the screencap shell command workaround already implemented in this repo
- Dark mode support detection requires two separate exploration passes

---

## Sample output

The `knowledge_pack/` folder in this repo contains a real scan of the Wikipedia Alpha app as a working sample. Open `knowledge_pack/viewer.html` in your browser to see the output.
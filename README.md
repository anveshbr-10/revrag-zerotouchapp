
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

On Windows use `.\gradlew.bat` instead of `./gradlew`.

### Step 6 — Create the output folder on device and run the explorer

Create the screenshots folder on the device:
```bash
adb shell mkdir -p /sdcard/knowledge_pack_screenshots
```

Open the target app on your phone and leave it in the foreground. Then run:
```bash
adb shell am instrument -w -r com.revrag.explorer.test/androidx.test.runner.AndroidJUnitRunner
```

The explorer will run for several minutes, tapping through the app automatically. Watch your phone — you will see it tapping. It will stop on its own when done or after hitting the step limit.

### Step 7 — Pull the captured data

Create the local knowledge pack folder:
```bash
mkdir -p knowledge_pack/raw
mkdir -p knowledge_pack/screenshots
```

Pull screenshots from device:
```bash
adb pull /sdcard/knowledge_pack_screenshots knowledge_pack/screenshots
```

Pull tree.xml files and transitions for each screen. First list what was captured:
```bash
adb shell run-as com.revrag.explorer ls cache/knowledge_pack/raw
```

For each hash folder shown, run:
```bash
mkdir knowledge_pack/raw/<hash>
adb shell run-as com.revrag.explorer cat cache/knowledge_pack/raw/<hash>/tree.xml > knowledge_pack/raw/<hash>/tree.xml
```

Pull transitions:
```bash
adb shell run-as com.revrag.explorer cat cache/knowledge_pack/raw/transitions.jsonl > knowledge_pack/raw/transitions.jsonl
```

Then copy each screenshot into its matching raw folder:
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
- `knowledge_pack/button_report.md` — human readable report (open in any markdown viewer)
- `knowledge_pack/app_knowledge_pack.json` — machine readable structured knowledge pack

---

## Optional passes

### Stability check

Run the explorer twice saving into separate folders, then compare:

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

Then run perceiver and synthesizer on each separately and merge:

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
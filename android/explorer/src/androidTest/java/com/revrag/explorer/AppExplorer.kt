/**
 * AppExplorer.kt
 *
 * Autonomous exploration loop for the RevRag "Zero-Touch App Understanding" challenge.
 * Runs as an Android Instrumented Test (androidx.test.uiautomator).
 *
 * What it does per step, in priority order:
 *  1. Dumps the accessibility tree of the current screen.
 *  2. Computes a STRUCTURAL hash of that screen (ignores pixel coordinates/screenshot
 *     content, so the same logical screen hashes the same way on repeat scans).
 *  3. Takes a screenshot and saves (screenshot, tree XML, hash, elements) to disk.
 *  4. If there's an unfilled text field on screen (login/OTP/KYC style forms), fills it
 *     with test data inferred from the field's hint (see [testDataByHint]) so the DFS
 *     can get past auth gates instead of stalling on them.
 *  5. Otherwise picks the next unvisited clickable element on this screen to tap.
 *  6. Otherwise, if the screen hasn't been scrolled yet, swipes down once to reveal any
 *     off-screen content (lists/feeds/long forms) before giving up on this screen.
 *  7. Otherwise backs out if every element here has already been tried/filled/scrolled,
 *     or we look "stuck".
 *
 * Pass -e raw_subdir <name> as an instrumentation argument to write this run under
 * knowledge_pack/raw/<name> instead of knowledge_pack/raw directly -- used to run a
 * light-mode pass and a dark-mode pass into separate folders (see dark_mode_check.py).
 *
 * Run with: ./gradlew connectedAndroidTest (targeting the app-under-test's package)
 */

package com.revrag.explorer

import android.graphics.Rect
import android.os.Environment
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.UiObject2
import org.junit.Test
import java.io.File
import java.security.MessageDigest
import java.util.LinkedList

data class ElementInfo(
    val resourceId: String?,
    val text: String?,
    val className: String?,
    val clickable: Boolean,
    val focusable: Boolean,
    val isPassword: Boolean,
    val bounds: Rect
) {
    /** Heuristic: editable text inputs are focusable and look like an EditText,
     *  regardless of whether they also happen to be clickable. */
    val isEditableField: Boolean
        get() = focusable && (className?.contains("EditText", ignoreCase = true) == true)
}

data class ScreenState(
    val hash: String,
    val elements: List<ElementInfo>,
    val treeXml: String
)

class AppExplorer {

    private val device: UiDevice =
        UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())
    
    private val targetPackage: String = "org.wikipedia.alpha"

    // Optional instrumentation arg (-e raw_subdir <name>) so a light-mode pass and a
    // dark-mode pass can be written to separate folders instead of overwriting each other.
    private val rawSubdir: String? =
        InstrumentationRegistry.getArguments().getString("raw_subdir")

    // Where every dump gets written for the Perceiver/Synthesizer step to pick up later.
    private val outDir: File = File(
    InstrumentationRegistry.getInstrumentation()
        .targetContext
        .cacheDir,
    if (rawSubdir.isNullOrBlank()) "knowledge_pack/raw" else "knowledge_pack/raw_$rawSubdir"
).apply { mkdirs() }

    private val visitedHashes = HashSet<String>()
    // Per-screen: which element indices (by a stable key) have already been tapped.
    private val triedElementsByScreen = HashMap<String, MutableSet<String>>()
    // Per-screen: which editable fields (by the same stable key) have already been filled.
    private val filledFieldsByScreen = HashMap<String, MutableSet<String>>()
    // Per-screen: whether we've already tried scrolling for more content.
    private val scrolledScreens = HashSet<String>()

    // Test data used to get past login/OTP/KYC-style gates during autonomous exploration.
    // Keyed by a lowercase substring matched against the field's resource-id/text/class --
    // extend this map for whatever the target app's fields are actually called.
    private val testDataByHint: List<Pair<String, String>> = listOf(
        "otp" to "123456",
        "pin" to "123456",
        "password" to "Test@1234",
        "confirm" to "Test@1234",
        "email" to "revrag.tester@example.com",
        "phone" to "9999999999",
        "mobile" to "9999999999",
        "username" to "revrag_tester",
        "name" to "Rev Rag Tester"
    )
    private val fallbackTestValue = "Test123"

    // Records {from_hash, element_key, element_label, to_hash} for every tap, so the
    // Synthesizer can reconstruct journeys (a graph of screens) after the fact.
    private val transitionsFile = File(outDir, "transitions.jsonl")

    private val maxSteps = 100          // hard budget so exploration always terminates
    private val stuckLimit = 3          // same hash this many times in a row -> back out
    private var consecutiveRepeats = 0
    private var lastHash: String? = null
    private var stepCount = 0

    // Set right after a tap/back-press, then flushed once we see the resulting screen.
    private var pendingTransition: Triple<String, String, String>? = null // from_hash, element_key, element_label

    @Test
    fun explore() {
        // Simple DFS-with-backtrack: at each screen, try the first untried clickable
        // element; if none remain, press back and continue from the parent screen.

        val launchIntent = InstrumentationRegistry.getInstrumentation()
            .context.packageManager.getLaunchIntentForPackage(targetPackage)
        if (launchIntent != null) {
            launchIntent.addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
            InstrumentationRegistry.getInstrumentation().context.startActivity(launchIntent)
            device.waitForIdle()
            Thread.sleep(3000)
        } else {
            device.executeShellCommand("monkey -p $targetPackage -c android.intent.category.LAUNCHER 1")
            device.waitForIdle()
            Thread.sleep(3000)
        }

        while (stepCount < maxSteps) {
            stepCount++
            device.waitForIdle()

            val state = captureState()
            persistState(state)
            flushPendingTransition(toHash = state.hash)

            if (device.currentPackageName != targetPackage) {
                device.pressBack()
                device.waitForIdle()
                Thread.sleep(1000)
                continue
            }

            if (state.hash == lastHash) {
                consecutiveRepeats++
            } else {
                consecutiveRepeats = 0
            }
            lastHash = state.hash

            if (consecutiveRepeats >= stuckLimit) {
                pendingTransition = Triple(state.hash, "BACK", "system back button")
                if (!device.pressBack()) break   // nowhere left to back out to -> done
                consecutiveRepeats = 0
                continue
            }

            // Priority 1: fill any not-yet-filled text field (login/OTP/KYC gates) so the
            // walk doesn't stall in front of a form it can never submit.
            val filled = filledFieldsByScreen.getOrPut(state.hash) { mutableSetOf() }
            val nextField = state.elements.firstOrNull { el ->
                el.isEditableField && elementKey(el) !in filled
            }
            if (nextField != null) {
                filled.add(elementKey(nextField))
                val value = inferTestValue(nextField)
                fillTextField(nextField, value)
                // Filling doesn't usually navigate anywhere, so it isn't logged as a
                // journey edge -- only real taps/backs are.
                continue
            }

            // Priority 2: tap the next untried clickable element.
            val tried = triedElementsByScreen.getOrPut(state.hash) { mutableSetOf() }
            val nextElement = state.elements.firstOrNull { el ->
                el.clickable && elementKey(el) !in tried
            }

            if (nextElement != null) {
                tried.add(elementKey(nextElement))
                pendingTransition = Triple(
                    state.hash,
                    elementKey(nextElement),
                    nextElement.text ?: nextElement.resourceId ?: nextElement.className ?: "unlabeled element"
                )
                tapElement(nextElement)
                continue
            }

            // Priority 3: nothing left to tap or fill -- try scrolling once for more
            // content (lists/feeds/long forms) before giving up on this screen.
            if (state.hash !in scrolledScreens) {
                scrolledScreens.add(state.hash)
                pendingTransition = Triple(state.hash, "SCROLL_DOWN", "scroll down for more content")
                scrollScreenDown()
                continue
            }

            // Priority 4: truly nothing new here; go back one level.
            pendingTransition = Triple(state.hash, "BACK", "system back button")
            if (!device.pressBack()) break
        }
    }

    /** Dumps the current accessibility tree + derives a stable structural hash. */
    private fun captureState(): ScreenState {
        val treeFile = File(outDir, "tmp_tree_$stepCount.xml")
        device.dumpWindowHierarchy(treeFile)
        val treeXml = treeFile.readText()
        treeFile.delete()

        val elements = parseElements(treeXml)

        // Structural signature: sorted (resourceId|className|text-presence) tuples.
        // Deliberately excludes bounds/coordinates and exact screenshot pixels so the
        // same logical screen produces the same hash across separate scans.
        val signature = elements
            .map { "${it.resourceId ?: ""}|${it.className ?: ""}|${it.text?.isNotBlank() ?: false}|${it.clickable}" }
            .sorted()
            .joinToString("\n")

        val hash = sha256(signature)
        return ScreenState(hash, elements, treeXml)
    }

    private fun persistState(state: ScreenState) {
        val screenDir = File(outDir, state.hash).apply { mkdirs() }

        // Only write once per unique screen (repeat visits don't need re-saving),
        // but always attempt the screenshot since app content can be dynamic.
        if (state.hash !in visitedHashes) {
            visitedHashes.add(state.hash)
            File(screenDir, "tree.xml").writeText(state.treeXml)
        }

        val screenshotFile = File(screenDir, "screenshot_$stepCount.png")
        device.takeScreenshot(screenshotFile)
        val sdcardDir = "/sdcard/knowledge_pack_screenshots"
        device.executeShellCommand("mkdir -p $sdcardDir")
        device.executeShellCommand("screencap -p $sdcardDir/${state.hash}.png")

        // Also save to sdcard for easy pulling
        val sdcardPath = "/sdcard/knowledge_pack_screenshots/${state.hash}_$stepCount.png"
        device.executeShellCommand("mkdir -p /sdcard/knowledge_pack_screenshots")
        device.executeShellCommand("cp ${screenshotFile.absolutePath} $sdcardPath")
    }

    private fun tapElement(el: ElementInfo) {
        val obj: UiObject2? = when {
            el.resourceId != null -> device.findObject(By.res(el.resourceId))
            el.text != null -> device.findObject(By.text(el.text))
            else -> null
        }
        obj?.click() ?: run {
            // Fallback: tap by bounds center if selector lookup failed.
            device.click(el.bounds.centerX(), el.bounds.centerY())
        }
        device.waitForIdle()
    }

    /** Writes the tap/back that led to [toHash] as one JSONL line, then clears it. */
    private fun flushPendingTransition(toHash: String) {
        val pending = pendingTransition ?: return
        val (fromHash, elementKey, elementLabel) = pending
        val escapedLabel = elementLabel.replace("\"", "\\\"")
        val line = """{"from_hash":"$fromHash","element_key":"$elementKey","element_label":"$escapedLabel","to_hash":"$toHash"}"""
        transitionsFile.appendText(line + "\n")
        pendingTransition = null
    }

    private fun elementKey(el: ElementInfo): String =
        el.resourceId ?: "${el.className}:${el.text}:${el.bounds}"

    private fun sha256(input: String): String =
        MessageDigest.getInstance("SHA-256")
            .digest(input.toByteArray())
            .joinToString("") { "%02x".format(it) }

    /**
     * Minimal accessibility-tree XML parser. Extracts each attribute independently
     * (rather than assuming a fixed attribute order in one combined regex) so it keeps
     * working regardless of how a given device/OS orders attributes in the dump. Swap
     * for a proper XML pull-parser (XmlPullParser) if you need attributes beyond these
     * six — kept simple here so the loop above is easy to read and debug under time
     * pressure.
     */
    private fun parseElements(xml: String): List<ElementInfo> {
        val nodeTagRegex = Regex("""<node\b[^>]*>""")
        val boundsRegex = Regex("""\[(\d+),(\d+)\]\[(\d+),(\d+)\]""")

        return nodeTagRegex.findAll(xml).mapNotNull { m ->
            val tag = m.value
            val boundsMatch = boundsRegex.find(attrValue(tag, "bounds") ?: "") ?: return@mapNotNull null
            val (l, t, r, b) = boundsMatch.destructured

            ElementInfo(
                resourceId = attrValue(tag, "resource-id")?.ifBlank { null },
                text = attrValue(tag, "text")?.ifBlank { null },
                className = attrValue(tag, "class")?.ifBlank { null },
                clickable = attrValue(tag, "clickable") == "true",
                focusable = attrValue(tag, "focusable") == "true",
                isPassword = attrValue(tag, "password") == "true",
                bounds = Rect(l.toInt(), t.toInt(), r.toInt(), b.toInt())
            )
        }.toList()
    }

    /** Pulls a single `name="value"` attribute out of one `<node ...>` opening tag.
     *  Requires whitespace (or tag start) right before the name, so looking up
     *  "clickable" doesn't accidentally match inside "long-clickable". */
    private fun attrValue(tag: String, name: String): String? =
        Regex("""(?:^|\s)$name="([^"]*)"""").find(tag)?.groupValues?.get(1)

    // ---------- form filling (login / OTP / KYC gates) ----------

    /** Picks a test value for [el] based on its resource-id/text/class, falling back to
     *  a generic value so unrecognized fields still get *something* rather than being
     *  skipped and stalling the DFS in front of a form it can't submit. */
    private fun inferTestValue(el: ElementInfo): String {
        val hintSource = listOfNotNull(el.resourceId, el.text, el.className)
            .joinToString(" ")
            .lowercase()
        testDataByHint.firstOrNull { (hint, _) -> hint in hintSource }?.let { (_, value) -> return value }
        if (el.isPassword) return "Test@1234"
        return fallbackTestValue
    }

    private fun fillTextField(el: ElementInfo, value: String) {
        val obj: UiObject2? = when {
            el.resourceId != null -> device.findObject(By.res(el.resourceId))
            else -> device.findObject(By.clazz(el.className ?: "android.widget.EditText"))
        }
        try {
            obj?.let {
                it.click()
                it.text = value
            }
        } catch (_: Exception) {
            // Some fields (custom OTP boxes, read-only spinners styled as EditText) reject
            // setText -- skip rather than crash the whole exploration run over one field.
        }
        device.waitForIdle()
    }

    // ---------- scrolling for off-screen content ----------

    private fun scrollScreenDown() {
        val width = device.displayWidth
        val height = device.displayHeight
        device.swipe(
            width / 2, (height * 0.8).toInt(),
            width / 2, (height * 0.2).toInt(),
            20 // steps -- higher = slower/smoother swipe
        )
        device.waitForIdle()
    }
}

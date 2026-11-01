package com.ragcommerce.agent

import android.app.UiAutomation
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Rect
import android.provider.Settings
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File
import java.util.concurrent.CopyOnWriteArrayList

/** Observes installed TalkBack. Host hardware events, never node actions, drive acceptance. */
class TalkBackTraversalTest {
    @Test fun observeNativeTalkBack() {
        val args = InstrumentationRegistry.getArguments()
        assumeTrue("Opt-in installed TalkBack QA", args.getString("talkBackQa") == "1")
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        val automation = instrumentation.getUiAutomation(UiAutomation.FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES)
        val service = "com.google.android.marvin.talkback/com.google.android.marvin.talkback.TalkBackService"
        assertTrue("Explicitly enable installed TalkBack before observation",
            Settings.Secure.getString(context.contentResolver, "enabled_accessibility_services").orEmpty().contains(service))
        val session = requireNotNull(args.getString("qaSession"))
        require(session.matches(Regex("[a-zA-Z0-9_-]+")))
        val directory = File(context.filesDir, "talkback/$session").apply { mkdirs() }
        val events = CopyOnWriteArrayList<JSONObject>()
        fun ownLabel(node: AccessibilityNodeInfo): String = listOf(node.text?.toString().orEmpty(), node.contentDescription?.toString().orEmpty())
            .filter { it.isNotBlank() }.distinct().joinToString(" · ")
        fun spokenLabel(node: AccessibilityNodeInfo): String = ownLabel(node).ifBlank {
            (0 until node.childCount).mapNotNull { node.getChild(it)?.let(::spokenLabel)?.takeIf(String::isNotBlank) }
                .distinct().joinToString(" · ")
        }
        fun describe(node: AccessibilityNodeInfo, path: String = ""): JSONObject {
            val bounds = Rect().also(node::getBoundsInScreen)
            return JSONObject().put("label", spokenLabel(node)).put("path", path)
                .put("id", node.viewIdResourceName).put("package", node.packageName)
                .put("class", node.className).put("clickable", node.isClickable)
                .put("enabled", node.isEnabled).put("selected", node.isSelected)
                .put("checkable", node.isCheckable).put("checked", node.isChecked)
                .put("editable", node.isEditable).put("heading", node.isHeading)
                .put("focused", node.isAccessibilityFocused).put("visible", node.isVisibleToUser)
                .put("scrollable", node.isScrollable).put("bounds", JSONArray(listOf(bounds.left, bounds.top, bounds.right, bounds.bottom)))
                .put("actions", JSONArray(node.actionList.map { it.id }))
        }
        automation.setOnAccessibilityEventListener { event ->
            if (event.eventType in listOf(AccessibilityEvent.TYPE_VIEW_ACCESSIBILITY_FOCUSED,
                    AccessibilityEvent.TYPE_VIEW_CLICKED, AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED,
                    AccessibilityEvent.TYPE_ANNOUNCEMENT, AccessibilityEvent.TYPE_VIEW_SCROLLED)) {
                val source = event.source?.let { describe(it) }
                if (source != null && source.optString("label").isBlank()) {
                    source.put("label", event.text.map { it.toString() }.filter(String::isNotBlank).joinToString(" · "))
                }
                events.add(JSONObject().put("type", event.eventType).put("time", event.eventTime)
                    .put("package", event.packageName).put("text", JSONArray(event.text.map { it.toString() }))
                    .put("source", source))
            }
        }
        if (args.getString("launchApp") == "1") {
            context.startActivity(Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        }
        val deadline = System.currentTimeMillis() + 1_200_000
        try {
            while (!File(directory, "stop").exists() && System.currentTimeMillis() < deadline) {
                val root = automation.rootInActiveWindow
                val visible = JSONArray()
                fun walk(node: AccessibilityNodeInfo, path: String) {
                    if (node.isVisibleToUser) visible.put(describe(node, path))
                    for (i in 0 until node.childCount) node.getChild(i)?.let { walk(it, "$path.$i") }
                }
                root?.let { walk(it, "0") }
                val focused = root?.findFocus(AccessibilityNodeInfo.FOCUS_ACCESSIBILITY)?.let { describe(it) }
                if (focused != null && focused.optString("label").isBlank()) {
                    val event = events.lastOrNull { it.optInt("type") == AccessibilityEvent.TYPE_VIEW_ACCESSIBILITY_FOCUSED }
                    val source = event?.optJSONObject("source")
                    if (source != null && source.optString("package") == focused.optString("package") &&
                        source.optJSONArray("bounds").toString() == focused.optJSONArray("bounds").toString()) {
                        focused.put("label", source.optString("label"))
                    }
                }
                val snapshot = JSONObject().put("session", session).put("observer_only", true)
                    .put("at", System.currentTimeMillis()).put("event_count", events.size)
                    .put("focus", focused)
                    .put("nodes", visible).put("events", JSONArray(events.toList()))
                val temporary = File(directory, "state.next.json")
                temporary.writeText(snapshot.toString())
                assertTrue("Publish one complete observation", temporary.renameTo(File(directory, "state.json")))
                if (File(directory, "capture").exists()) {
                    automation.takeScreenshot()?.let { bitmap ->
                        File(directory, "screen.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
                        bitmap.recycle()
                    }
                    File(directory, "capture").delete()
                }
                Thread.sleep(200)
            }
            assertTrue("Host must explicitly end observation; timeout is not acceptance", File(directory, "stop").exists())
        } finally {
            automation.setOnAccessibilityEventListener(null)
        }
    }
}

package com.devicekit.agent.services

import android.accessibilityservice.AccessibilityService
import android.util.Log
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import com.devicekit.agent.DeviceState
import com.devicekit.agent.api.DeviceKitClient
import kotlinx.coroutines.*

/**
 * Accessibility Service that detects:
 * - When a text input field is focused (keyboard wants to appear)
 * - Which field is focused (resource ID, type, current text)
 * - Window/activity changes
 * - UI content changes
 *
 * This is the key service that answers "does the device want to type something?"
 */
class AccessibilityAgent : AccessibilityService() {

    companion object {
        private const val TAG = "AccessibilityAgent"
        var isRunning: Boolean = false
            private set
    }

    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private val client = DeviceKitClient()

    override fun onServiceConnected() {
        super.onServiceConnected()
        isRunning = true
        Log.i(TAG, "Accessibility Agent connected")
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        event ?: return

        when (event.eventType) {
            AccessibilityEvent.TYPE_VIEW_FOCUSED -> handleFocusChange(event)
            AccessibilityEvent.TYPE_VIEW_TEXT_CHANGED -> handleTextChanged(event)
            AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED -> handleWindowChange(event)
            AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED -> handleContentChange(event)
            AccessibilityEvent.TYPE_NOTIFICATION_STATE_CHANGED -> handleNotification(event)
        }
    }

    /**
     * A view received focus. Check if it's an editable text field,
     * which means the keyboard is about to appear or is expected.
     */
    private fun handleFocusChange(event: AccessibilityEvent) {
        val source = event.source ?: return

        val isEditable = source.isEditable
        val className = source.className?.toString() ?: ""
        val viewId = source.viewIdResourceName
        val text = source.text?.toString() ?: ""

        // Detect if this is a text input field
        val isInputField = isEditable ||
            className.contains("EditText") ||
            className.contains("AutoCompleteTextView") ||
            className.contains("SearchView")

        if (isInputField) {
            DeviceState.isKeyboardVisible = true
            DeviceState.focusedFieldId = viewId
            DeviceState.focusedFieldType = extractInputType(source)
            DeviceState.focusedFieldText = text
            DeviceState.focusedPackage = event.packageName?.toString()
            DeviceState.focusedClassName = className

            Log.d(TAG, "Input field focused: $viewId (type=$className, pkg=${event.packageName})")

            // Notify server about keyboard/input event
            reportInputEvent("field_focused", viewId, className)
        } else {
            // Non-input view focused - keyboard might be dismissing
            DeviceState.isKeyboardVisible = false
            DeviceState.focusedFieldId = null
            DeviceState.focusedFieldType = null
            DeviceState.focusedFieldText = null
        }

        source.recycle()
    }

    /**
     * Text changed in a focused field - the user (or automation) is typing.
     */
    private fun handleTextChanged(event: AccessibilityEvent) {
        val text = event.text?.mapNotNull { it?.toString() }?.joinToString("") ?: ""
        DeviceState.focusedFieldText = text

        Log.d(TAG, "Text changed: ${text.take(50)}...")
    }

    /**
     * Window/activity changed - update current app context.
     */
    private fun handleWindowChange(event: AccessibilityEvent) {
        val pkg = event.packageName?.toString()
        val cls = event.className?.toString()

        if (pkg != null) {
            DeviceState.currentPackage = pkg
            DeviceState.currentActivity = cls

            // Check if an input method window appeared (keyboard shown)
            if (pkg.contains("inputmethod") || cls?.contains("InputMethod") == true) {
                DeviceState.isKeyboardVisible = true
                Log.d(TAG, "Keyboard appeared: $pkg")
                reportInputEvent("keyboard_shown", null, null)
            }
        }
    }

    /**
     * Content changed in current window - can detect dynamic UI updates.
     */
    private fun handleContentChange(event: AccessibilityEvent) {
        // Lightweight: only update package tracking
        event.packageName?.toString()?.let { pkg ->
            if (!pkg.contains("systemui")) {
                DeviceState.currentPackage = pkg
            }
        }
    }

    private fun handleNotification(event: AccessibilityEvent) {
        val notification = event.parcelableData
        if (notification is android.app.Notification) {
            val extras = notification.extras
            DeviceState.addNotification(
                DeviceState.NotificationInfo(
                    packageName = event.packageName?.toString() ?: "unknown",
                    title = extras?.getString("android.title"),
                    text = extras?.getString("android.text"),
                    timestamp = System.currentTimeMillis()
                )
            )
        }
    }

    /**
     * Extract input type hint from accessibility node.
     */
    private fun extractInputType(node: AccessibilityNodeInfo): String {
        return when {
            node.isPassword -> "password"
            node.className?.contains("EditText") == true -> "text"
            node.className?.contains("AutoComplete") == true -> "autocomplete"
            node.className?.contains("Search") == true -> "search"
            else -> "unknown"
        }
    }

    private fun reportInputEvent(eventType: String, fieldId: String?, fieldClass: String?) {
        val deviceId = DeviceState.deviceId ?: return
        scope.launch {
            try {
                val data = org.json.JSONObject().apply {
                    put("keyboard_visible", DeviceState.isKeyboardVisible)
                    put("field_id", fieldId)
                    put("field_class", fieldClass)
                    put("package", DeviceState.focusedPackage)
                }
                client.reportEvent(deviceId, eventType, data)
            } catch (e: Exception) {
                Log.w(TAG, "Failed to report input event: ${e.message}")
            }
        }
    }

    override fun onInterrupt() {
        Log.w(TAG, "Accessibility Agent interrupted")
    }

    override fun onDestroy() {
        super.onDestroy()
        isRunning = false
        scope.cancel()
        Log.i(TAG, "Accessibility Agent destroyed")
    }
}

package com.devicekit.agent.server.routes

import android.content.Context
import android.view.accessibility.AccessibilityNodeInfo
import com.devicekit.agent.server.*
import com.devicekit.agent.services.AccessibilityAgent
import fi.iki.elonen.NanoHTTPD
import org.json.JSONArray
import org.json.JSONObject

class UiRoutes(private val context: Context) : RouteHandler {

    override fun handle(
        method: NanoHTTPD.Method,
        uri: String,
        session: NanoHTTPD.IHTTPSession,
        bodyParams: Map<String, String>
    ): NanoHTTPD.Response? {
        if (method != NanoHTTPD.Method.POST) return null

        return when (uri) {
            "/ui/dump" -> handleDump()
            "/ui/find" -> handleFind(session, bodyParams)
            "/ui/click" -> handleClick(session, bodyParams)
            "/ui/long_click" -> handleLongClick(session, bodyParams)
            "/ui/scroll" -> handleScroll(session, bodyParams)
            "/ui/set_text" -> handleSetText(session, bodyParams)
            "/ui/clear_text" -> handleClearText(session, bodyParams)
            "/ui/wait" -> handleWait(session, bodyParams)
            "/ui/exists" -> handleExists(session, bodyParams)
            else -> null
        }
    }

    private fun getRootNode(): AccessibilityNodeInfo? {
        val service = AccessibilityAgent.instance ?: return null
        return try {
            service.rootInActiveWindow
        } catch (e: Exception) {
            null
        }
    }

    private fun handleDump(): NanoHTTPD.Response {
        val root = getRootNode()
            ?: return errorResponse(message = "Accessibility service not available. Enable it in Settings.")
        val tree = UiHierarchyDumper.dumpTree(root)
        return jsonResponse(json = tree)
    }

    private fun handleFind(session: NanoHTTPD.IHTTPSession, bodyParams: Map<String, String>): NanoHTTPD.Response {
        val body = parseJsonBody(session, bodyParams)
        val root = getRootNode()
            ?: return errorResponse(message = "Accessibility service not available")

        val nodes = UiHierarchyDumper.findNodes(
            root,
            text = body.optStringOrNull("text"),
            resourceId = body.optStringOrNull("resourceId"),
            className = body.optStringOrNull("className"),
            description = body.optStringOrNull("description"),
            checkable = body.optBoolOrNull("checkable"),
            checked = body.optBoolOrNull("checked"),
            clickable = body.optBoolOrNull("clickable"),
            enabled = body.optBoolOrNull("enabled"),
            focusable = body.optBoolOrNull("focusable"),
            scrollable = body.optBoolOrNull("scrollable"),
            instance = body.optIntOrNull("instance")
        )

        val results = JSONArray()
        nodes.forEach { results.put(it) }

        return jsonResponse(json = JSONObject().apply {
            put("nodes", results)
            put("count", results.length())
        })
    }

    private fun handleClick(session: NanoHTTPD.IHTTPSession, bodyParams: Map<String, String>): NanoHTTPD.Response {
        val body = parseJsonBody(session, bodyParams)
        val root = getRootNode()
            ?: return errorResponse(message = "Accessibility service not available")

        val nodes = findBySelector(root, body)
        if (nodes.isEmpty()) {
            return jsonResponse(json = JSONObject().apply {
                put("success", false)
                put("error", "No matching node found")
            })
        }

        val node = nodes.first()
        val bounds = node.optJSONObject("bounds")
        if (bounds != null) {
            val cx = (bounds.getInt("left") + bounds.getInt("right")) / 2
            val cy = (bounds.getInt("top") + bounds.getInt("bottom")) / 2
            execShell("input tap $cx $cy")
            return jsonResponse(json = JSONObject().apply {
                put("success", true)
                put("x", cx)
                put("y", cy)
                put("node", node)
            })
        }

        return jsonResponse(json = JSONObject().apply {
            put("success", false)
            put("error", "No bounds for node")
        })
    }

    private fun handleLongClick(session: NanoHTTPD.IHTTPSession, bodyParams: Map<String, String>): NanoHTTPD.Response {
        val body = parseJsonBody(session, bodyParams)
        val root = getRootNode()
            ?: return errorResponse(message = "Accessibility service not available")

        val nodes = findBySelector(root, body)
        if (nodes.isEmpty()) {
            return jsonResponse(json = JSONObject().apply {
                put("success", false)
                put("error", "No matching node found")
            })
        }

        val node = nodes.first()
        val bounds = node.optJSONObject("bounds")
        if (bounds != null) {
            val cx = (bounds.getInt("left") + bounds.getInt("right")) / 2
            val cy = (bounds.getInt("top") + bounds.getInt("bottom")) / 2
            val duration = body.optInt("duration", 1000)
            execShell("input swipe $cx $cy $cx $cy $duration")
            return jsonResponse(json = JSONObject().apply {
                put("success", true)
                put("x", cx)
                put("y", cy)
            })
        }
        return jsonResponse(json = JSONObject().apply {
            put("success", false)
            put("error", "No bounds for node")
        })
    }

    private fun handleScroll(session: NanoHTTPD.IHTTPSession, bodyParams: Map<String, String>): NanoHTTPD.Response {
        val body = parseJsonBody(session, bodyParams)
        val direction = body.optString("direction", "down")

        val root = getRootNode()
        // If selector provided, find scrollable container
        val hasSelector = body.has("text") || body.has("resourceId") || body.has("className")
        val bounds = if (hasSelector && root != null) {
            val nodes = findBySelector(root, body)
            nodes.firstOrNull()?.optJSONObject("bounds")
        } else {
            null
        }

        // Default to screen center
        val screenResult = execShell("wm size")
        val sizeMatch = Regex("""(\d+)x(\d+)""").find(screenResult.output)
        val sw = sizeMatch?.groupValues?.get(1)?.toIntOrNull() ?: 1080
        val sh = sizeMatch?.groupValues?.get(2)?.toIntOrNull() ?: 1920

        val cx = if (bounds != null) (bounds.getInt("left") + bounds.getInt("right")) / 2 else sw / 2
        val cy = if (bounds != null) (bounds.getInt("top") + bounds.getInt("bottom")) / 2 else sh / 2
        val dist = if (bounds != null) {
            (bounds.getInt("bottom") - bounds.getInt("top")) * 2 / 3
        } else {
            sh / 3
        }

        val (x1, y1, x2, y2) = when (direction) {
            "up" -> listOf(cx, cy - dist / 2, cx, cy + dist / 2)
            "down" -> listOf(cx, cy + dist / 2, cx, cy - dist / 2)
            "left" -> listOf(cx - dist / 2, cy, cx + dist / 2, cy)
            "right" -> listOf(cx + dist / 2, cy, cx - dist / 2, cy)
            else -> listOf(cx, cy + dist / 2, cx, cy - dist / 2)
        }

        val result = execShell("input swipe $x1 $y1 $x2 $y2 300")
        return jsonResponse(json = JSONObject().apply {
            put("success", result.exitCode == 0)
            put("direction", direction)
        })
    }

    private fun handleSetText(session: NanoHTTPD.IHTTPSession, bodyParams: Map<String, String>): NanoHTTPD.Response {
        val body = parseJsonBody(session, bodyParams)
        val text = body.optString("text", "")

        val root = getRootNode()
            ?: return errorResponse(message = "Accessibility service not available")

        // Find the node and click it first to focus
        val nodes = findBySelector(root, body)
        if (nodes.isEmpty()) {
            return jsonResponse(json = JSONObject().apply {
                put("success", false)
                put("error", "No matching node found")
            })
        }

        val node = nodes.first()
        val bounds = node.optJSONObject("bounds")
        if (bounds != null) {
            val cx = (bounds.getInt("left") + bounds.getInt("right")) / 2
            val cy = (bounds.getInt("top") + bounds.getInt("bottom")) / 2
            // Tap to focus
            execShell("input tap $cx $cy")
            Thread.sleep(200)
            // Select all and delete existing text
            execShell("input keyevent KEYCODE_MOVE_HOME")
            execShell("input keyevent --longpress KEYCODE_MOVE_END")
            execShell("input keyevent KEYCODE_DEL")
            // Type new text
            if (text.isNotEmpty()) {
                val escaped = text.replace(" ", "%s")
                execShell("input text \"$escaped\"")
            }
        }

        return jsonResponse(json = JSONObject().apply {
            put("success", true)
            put("text", text)
        })
    }

    private fun handleClearText(session: NanoHTTPD.IHTTPSession, bodyParams: Map<String, String>): NanoHTTPD.Response {
        val body = parseJsonBody(session, bodyParams)
        val root = getRootNode()
            ?: return errorResponse(message = "Accessibility service not available")

        val nodes = findBySelector(root, body)
        if (nodes.isEmpty()) {
            return jsonResponse(json = JSONObject().apply {
                put("success", false)
                put("error", "No matching node found")
            })
        }

        val node = nodes.first()
        val bounds = node.optJSONObject("bounds")
        if (bounds != null) {
            val cx = (bounds.getInt("left") + bounds.getInt("right")) / 2
            val cy = (bounds.getInt("top") + bounds.getInt("bottom")) / 2
            execShell("input tap $cx $cy")
            Thread.sleep(200)
            execShell("input keyevent KEYCODE_MOVE_HOME")
            execShell("input keyevent --longpress KEYCODE_MOVE_END")
            execShell("input keyevent KEYCODE_DEL")
        }

        return jsonResponse(json = JSONObject().apply {
            put("success", true)
        })
    }

    private fun handleWait(session: NanoHTTPD.IHTTPSession, bodyParams: Map<String, String>): NanoHTTPD.Response {
        val body = parseJsonBody(session, bodyParams)
        val timeout = body.optInt("timeout", 10) * 1000L
        val interval = 500L
        val elapsed = mutableListOf(0L)

        while (elapsed[0] < timeout) {
            val root = getRootNode()
            if (root != null) {
                val nodes = findBySelector(root, body)
                if (nodes.isNotEmpty()) {
                    return jsonResponse(json = JSONObject().apply {
                        put("found", true)
                        put("elapsed_ms", elapsed[0])
                        put("node", nodes.first())
                    })
                }
            }
            Thread.sleep(interval)
            elapsed[0] += interval
        }

        return jsonResponse(json = JSONObject().apply {
            put("found", false)
            put("elapsed_ms", elapsed[0])
        })
    }

    private fun handleExists(session: NanoHTTPD.IHTTPSession, bodyParams: Map<String, String>): NanoHTTPD.Response {
        val body = parseJsonBody(session, bodyParams)
        val timeout = body.optInt("timeout", 0) * 1000L

        if (timeout > 0) {
            val interval = 500L
            var elapsed = 0L
            while (elapsed < timeout) {
                val root = getRootNode()
                if (root != null) {
                    val nodes = findBySelector(root, body)
                    if (nodes.isNotEmpty()) {
                        return jsonResponse(json = JSONObject().apply {
                            put("exists", true)
                        })
                    }
                }
                Thread.sleep(interval)
                elapsed += interval
            }
            return jsonResponse(json = JSONObject().apply {
                put("exists", false)
            })
        }

        val root = getRootNode()
        if (root == null) {
            return jsonResponse(json = JSONObject().apply {
                put("exists", false)
            })
        }
        val nodes = findBySelector(root, body)
        return jsonResponse(json = JSONObject().apply {
            put("exists", nodes.isNotEmpty())
        })
    }

    private fun findBySelector(root: AccessibilityNodeInfo, body: JSONObject): List<JSONObject> {
        return UiHierarchyDumper.findNodes(
            root,
            text = body.optStringOrNull("text"),
            resourceId = body.optStringOrNull("resourceId"),
            className = body.optStringOrNull("className"),
            description = body.optStringOrNull("description"),
            checkable = body.optBoolOrNull("checkable"),
            checked = body.optBoolOrNull("checked"),
            clickable = body.optBoolOrNull("clickable"),
            enabled = body.optBoolOrNull("enabled"),
            focusable = body.optBoolOrNull("focusable"),
            scrollable = body.optBoolOrNull("scrollable"),
            instance = body.optIntOrNull("instance")
        )
    }
}

// Extension helpers
fun JSONObject.optStringOrNull(key: String): String? {
    return if (has(key) && !isNull(key)) optString(key) else null
}

fun JSONObject.optBoolOrNull(key: String): Boolean? {
    return if (has(key) && !isNull(key)) optBoolean(key) else null
}

fun JSONObject.optIntOrNull(key: String): Int? {
    return if (has(key) && !isNull(key)) optInt(key) else null
}

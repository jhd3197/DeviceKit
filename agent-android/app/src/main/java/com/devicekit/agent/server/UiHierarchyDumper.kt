package com.devicekit.agent.server

import android.view.accessibility.AccessibilityNodeInfo
import org.json.JSONArray
import org.json.JSONObject

/**
 * Walks the AccessibilityNodeInfo tree and converts it to JSON.
 * Used by UiRoutes for /ui/dump, /ui/find, etc.
 */
object UiHierarchyDumper {

    /**
     * Dump the full UI tree starting from root node.
     */
    fun dumpTree(root: AccessibilityNodeInfo?): JSONObject {
        if (root == null) {
            return JSONObject().apply { put("error", "No root node available") }
        }
        return try {
            val tree = dumpNode(root, 0)
            root.recycle()
            tree
        } catch (e: Exception) {
            JSONObject().apply { put("error", e.message) }
        }
    }

    /**
     * Find all nodes matching the given selector criteria.
     */
    fun findNodes(
        root: AccessibilityNodeInfo?,
        text: String? = null,
        resourceId: String? = null,
        className: String? = null,
        description: String? = null,
        checkable: Boolean? = null,
        checked: Boolean? = null,
        clickable: Boolean? = null,
        enabled: Boolean? = null,
        focusable: Boolean? = null,
        scrollable: Boolean? = null,
        instance: Int? = null
    ): List<JSONObject> {
        if (root == null) return emptyList()

        val results = mutableListOf<JSONObject>()
        collectMatchingNodes(root, results, text, resourceId, className, description,
            checkable, checked, clickable, enabled, focusable, scrollable)
        root.recycle()

        if (instance != null && instance < results.size) {
            return listOf(results[instance])
        }
        return results
    }

    private fun collectMatchingNodes(
        node: AccessibilityNodeInfo,
        results: MutableList<JSONObject>,
        text: String?,
        resourceId: String?,
        className: String?,
        description: String?,
        checkable: Boolean?,
        checked: Boolean?,
        clickable: Boolean?,
        enabled: Boolean?,
        focusable: Boolean?,
        scrollable: Boolean?
    ) {
        if (matchesSelector(node, text, resourceId, className, description,
                checkable, checked, clickable, enabled, focusable, scrollable)) {
            results.add(nodeToJson(node))
        }
        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            collectMatchingNodes(child, results, text, resourceId, className, description,
                checkable, checked, clickable, enabled, focusable, scrollable)
            child.recycle()
        }
    }

    private fun matchesSelector(
        node: AccessibilityNodeInfo,
        text: String?,
        resourceId: String?,
        className: String?,
        description: String?,
        checkable: Boolean?,
        checked: Boolean?,
        clickable: Boolean?,
        enabled: Boolean?,
        focusable: Boolean?,
        scrollable: Boolean?
    ): Boolean {
        if (text != null) {
            val nodeText = node.text?.toString() ?: ""
            if (!nodeText.contains(text, ignoreCase = true)) return false
        }
        if (resourceId != null) {
            val nodeId = node.viewIdResourceName ?: ""
            if (!nodeId.contains(resourceId)) return false
        }
        if (className != null) {
            val nodeCls = node.className?.toString() ?: ""
            if (!nodeCls.contains(className)) return false
        }
        if (description != null) {
            val nodeDesc = node.contentDescription?.toString() ?: ""
            if (!nodeDesc.contains(description, ignoreCase = true)) return false
        }
        if (checkable != null && node.isCheckable != checkable) return false
        if (checked != null && node.isChecked != checked) return false
        if (clickable != null && node.isClickable != clickable) return false
        if (enabled != null && node.isEnabled != enabled) return false
        if (focusable != null && node.isFocusable != focusable) return false
        if (scrollable != null && node.isScrollable != scrollable) return false
        return true
    }

    private fun dumpNode(node: AccessibilityNodeInfo, depth: Int): JSONObject {
        val json = nodeToJson(node)
        if (node.childCount > 0) {
            val children = JSONArray()
            for (i in 0 until node.childCount) {
                val child = node.getChild(i) ?: continue
                children.put(dumpNode(child, depth + 1))
                child.recycle()
            }
            json.put("children", children)
        }
        return json
    }

    private fun nodeToJson(node: AccessibilityNodeInfo): JSONObject {
        val rect = android.graphics.Rect()
        node.getBoundsInScreen(rect)
        return JSONObject().apply {
            put("class", node.className?.toString())
            put("resource_id", node.viewIdResourceName)
            put("text", node.text?.toString())
            put("content_desc", node.contentDescription?.toString())
            put("package", node.packageName?.toString())
            put("checkable", node.isCheckable)
            put("checked", node.isChecked)
            put("clickable", node.isClickable)
            put("enabled", node.isEnabled)
            put("focusable", node.isFocusable)
            put("focused", node.isFocused)
            put("scrollable", node.isScrollable)
            put("long_clickable", node.isLongClickable)
            put("selected", node.isSelected)
            put("editable", node.isEditable)
            put("visible", node.isVisibleToUser)
            put("bounds", JSONObject().apply {
                put("left", rect.left)
                put("top", rect.top)
                put("right", rect.right)
                put("bottom", rect.bottom)
            })
        }
    }
}

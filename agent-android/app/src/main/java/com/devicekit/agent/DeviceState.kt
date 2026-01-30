package com.devicekit.agent

import org.json.JSONArray
import org.json.JSONObject

/**
 * Singleton holding current device state reported by all agent services.
 * The BackgroundAgent reads this and pushes it to the DeviceKit server.
 */
object DeviceState {

    // Keyboard / input state
    @Volatile var isKeyboardVisible: Boolean = false
    @Volatile var focusedFieldId: String? = null
    @Volatile var focusedFieldType: String? = null
    @Volatile var focusedFieldText: String? = null
    @Volatile var focusedPackage: String? = null
    @Volatile var focusedClassName: String? = null

    // Current window state
    @Volatile var currentPackage: String? = null
    @Volatile var currentActivity: String? = null

    // Notifications
    private val _recentNotifications = mutableListOf<NotificationInfo>()
    val recentNotifications: List<NotificationInfo> get() = _recentNotifications.toList()

    // Clipboard
    @Volatile var lastClipboardText: String? = null

    // Connection
    @Volatile var serverUrl: String = BuildConfig.DEVICEKIT_SERVER_URL
    @Volatile var isConnected: Boolean = false
    @Volatile var deviceId: String? = null

    // Metrics
    private const val MAX_HISTORY = 60
    @Volatile var latestMetrics: MetricsSnapshot? = null
    private val _metricsHistory = ArrayDeque<MetricsSnapshot>()

    val metricsHistory: List<MetricsSnapshot>
        get() = synchronized(_metricsHistory) { _metricsHistory.toList() }

    data class MetricsSnapshot(
        val cpuPercent: Double = 0.0,
        val ramUsedMb: Long = 0,
        val ramTotalMb: Long = 0,
        val batteryLevel: Int = 0,
        val batteryTemperature: Double = 0.0,
        val isCharging: Boolean = false,
        val networkType: String = "unknown",
        val networkRxRate: Long = 0,
        val networkTxRate: Long = 0,
        val timestamp: Long = System.currentTimeMillis()
    )

    data class NotificationInfo(
        val packageName: String,
        val title: String?,
        val text: String?,
        val timestamp: Long
    )

    fun updateMetrics(snapshot: MetricsSnapshot) {
        latestMetrics = snapshot
        synchronized(_metricsHistory) {
            if (_metricsHistory.size >= MAX_HISTORY) {
                _metricsHistory.removeFirst()
            }
            _metricsHistory.addLast(snapshot)
        }
    }

    fun addNotification(info: NotificationInfo) {
        synchronized(_recentNotifications) {
            _recentNotifications.add(0, info)
            if (_recentNotifications.size > 50) {
                _recentNotifications.removeAt(_recentNotifications.lastIndex)
            }
        }
    }

    fun clearNotifications() {
        synchronized(_recentNotifications) {
            _recentNotifications.clear()
        }
    }

    fun toJson(): JSONObject = JSONObject().apply {
        put("keyboard", JSONObject().apply {
            put("visible", isKeyboardVisible)
            put("focused_field_id", focusedFieldId)
            put("focused_field_type", focusedFieldType)
            put("focused_field_text", focusedFieldText)
            put("focused_package", focusedPackage)
            put("focused_class", focusedClassName)
        })
        put("window", JSONObject().apply {
            put("package", currentPackage)
            put("activity", currentActivity)
        })
        put("clipboard", lastClipboardText)
        put("notifications", JSONArray().apply {
            recentNotifications.take(10).forEach { n ->
                put(JSONObject().apply {
                    put("package", n.packageName)
                    put("title", n.title)
                    put("text", n.text)
                    put("timestamp", n.timestamp)
                })
            }
        })
        put("connected", isConnected)
        put("device_id", deviceId)

        // Metrics
        latestMetrics?.let { m ->
            put("metrics", JSONObject().apply {
                put("cpu_percent", Math.round(m.cpuPercent * 10.0) / 10.0)
                put("ram_used_mb", m.ramUsedMb)
                put("ram_total_mb", m.ramTotalMb)
                put("battery_level", m.batteryLevel)
                put("battery_temperature", m.batteryTemperature)
                put("is_charging", m.isCharging)
                put("network", JSONObject().apply {
                    put("type", m.networkType)
                    put("rx_rate", m.networkRxRate)
                    put("tx_rate", m.networkTxRate)
                })
            })
        }
    }

    fun toDisplayString(): String = buildString {
        appendLine("== Keyboard ==")
        appendLine("  visible: $isKeyboardVisible")
        appendLine("  field_id: ${focusedFieldId ?: "-"}")
        appendLine("  field_type: ${focusedFieldType ?: "-"}")
        appendLine("  field_text: ${focusedFieldText ?: "-"}")
        appendLine("  package: ${focusedPackage ?: "-"}")
        appendLine()
        appendLine("== Window ==")
        appendLine("  package: ${currentPackage ?: "-"}")
        appendLine("  activity: ${currentActivity ?: "-"}")
        appendLine()
        appendLine("== Connection ==")
        appendLine("  server: $serverUrl")
        appendLine("  connected: $isConnected")
        appendLine("  device_id: ${deviceId ?: "-"}")
        appendLine()
        latestMetrics?.let { m ->
            appendLine("== Metrics ==")
            appendLine("  cpu: ${String.format("%.1f", m.cpuPercent)}%")
            appendLine("  ram: ${String.format("%.1f", m.ramUsedMb / 1024.0)}/${String.format("%.1f", m.ramTotalMb / 1024.0)} GB")
            appendLine("  battery: ${m.batteryLevel}% ${if (m.isCharging) "(charging)" else ""}")
            appendLine("  temp: ${m.batteryTemperature}\u00B0C")
            appendLine("  network: ${m.networkType} rx:${m.networkRxRate} tx:${m.networkTxRate} B/s")
            appendLine()
        }
        appendLine("== Notifications (${recentNotifications.size}) ==")
        recentNotifications.take(5).forEach { n ->
            appendLine("  [${n.packageName}] ${n.title}: ${n.text}")
        }
    }
}

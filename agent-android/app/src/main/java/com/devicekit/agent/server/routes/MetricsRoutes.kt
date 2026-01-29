package com.devicekit.agent.server.routes

import android.content.Context
import com.devicekit.agent.DeviceState
import com.devicekit.agent.server.*
import fi.iki.elonen.NanoHTTPD
import org.json.JSONArray
import org.json.JSONObject

class MetricsRoutes(private val context: Context) : RouteHandler {

    override fun handle(
        method: NanoHTTPD.Method,
        uri: String,
        session: NanoHTTPD.IHTTPSession,
        bodyParams: Map<String, String>
    ): NanoHTTPD.Response? {
        if (method != NanoHTTPD.Method.GET) return null
        return when (uri) {
            "/metrics" -> handleSnapshot()
            "/metrics/history" -> handleHistory()
            else -> null
        }
    }

    private fun handleSnapshot(): NanoHTTPD.Response {
        val m = DeviceState.latestMetrics
        if (m == null) {
            return jsonResponse(json = JSONObject().apply {
                put("error", "No metrics available yet")
            })
        }
        return jsonResponse(json = metricsToJson(m))
    }

    private fun handleHistory(): NanoHTTPD.Response {
        val history = JSONArray()
        DeviceState.metricsHistory.forEach { m ->
            history.put(metricsToJson(m))
        }
        return jsonResponse(json = JSONObject().apply {
            put("history", history)
            put("count", history.length())
        })
    }

    private fun metricsToJson(m: DeviceState.MetricsSnapshot): JSONObject {
        return JSONObject().apply {
            put("cpu_percent", Math.round(m.cpuPercent * 10.0) / 10.0)
            put("ram_used_mb", m.ramUsedMb)
            put("ram_total_mb", m.ramTotalMb)
            put("battery_level", m.batteryLevel)
            put("battery_temperature", m.batteryTemperature)
            put("is_charging", m.isCharging)
            put("network_type", m.networkType)
            put("network_rx_rate", m.networkRxRate)
            put("network_tx_rate", m.networkTxRate)
            put("timestamp", m.timestamp)
        }
    }
}

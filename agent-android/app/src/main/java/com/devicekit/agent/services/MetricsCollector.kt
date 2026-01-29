package com.devicekit.agent.services

import android.app.ActivityManager
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.TrafficStats
import android.os.BatteryManager
import android.util.Log
import com.devicekit.agent.DeviceState
import com.devicekit.agent.server.routes.EventRoutes
import kotlinx.coroutines.*
import org.json.JSONObject
import java.io.RandomAccessFile

/**
 * Collects on-device metrics (CPU, RAM, battery, network) every 2 seconds.
 * Writes snapshots to DeviceState so they are included in server state reports.
 */
class MetricsCollector(private val context: Context) {

    companion object {
        private const val TAG = "MetricsCollector"
        private const val SAMPLE_INTERVAL_MS = 2_000L
    }

    private var scope: CoroutineScope? = null
    private var job: Job? = null

    // Previous CPU sample for delta calculation
    private var prevCpuTotal: Long = 0
    private var prevCpuIdle: Long = 0

    // Previous network bytes for rate calculation
    private var prevRxBytes: Long = 0
    private var prevTxBytes: Long = 0
    private var prevNetworkTimestamp: Long = 0

    fun start() {
        if (job?.isActive == true) return
        scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
        job = scope?.launch {
            // Take initial CPU and network samples
            readCpuSample()
            readNetworkBytes()
            prevNetworkTimestamp = System.currentTimeMillis()

            delay(SAMPLE_INTERVAL_MS)

            while (isActive) {
                try {
                    collectSnapshot()
                } catch (e: Exception) {
                    Log.w(TAG, "Metrics collection error: ${e.message}")
                }
                delay(SAMPLE_INTERVAL_MS)
            }
        }
        Log.i(TAG, "Metrics collection started")
    }

    fun stop() {
        job?.cancel()
        scope?.cancel()
        job = null
        scope = null
        Log.i(TAG, "Metrics collection stopped")
    }

    private fun collectSnapshot() {
        val cpuPercent = readCpuPercent()
        val ramInfo = readRamInfo()
        val batteryInfo = readBatteryInfo()
        val networkInfo = readNetworkInfo()

        val snapshot = DeviceState.MetricsSnapshot(
            cpuPercent = cpuPercent,
            ramUsedMb = ramInfo.first,
            ramTotalMb = ramInfo.second,
            batteryLevel = batteryInfo.level,
            batteryTemperature = batteryInfo.temperature,
            isCharging = batteryInfo.isCharging,
            networkType = networkInfo.type,
            networkRxRate = networkInfo.rxRate,
            networkTxRate = networkInfo.txRate,
            timestamp = System.currentTimeMillis()
        )

        DeviceState.updateMetrics(snapshot)

        // Broadcast to SSE clients
        EventRoutes.broadcast("metrics", JSONObject().apply {
            put("cpu_percent", Math.round(cpuPercent * 10.0) / 10.0)
            put("ram_used_mb", ramInfo.first)
            put("ram_total_mb", ramInfo.second)
            put("battery_level", batteryInfo.level)
            put("is_charging", batteryInfo.isCharging)
            put("network_type", networkInfo.type)
            put("timestamp", snapshot.timestamp)
        })
    }

    // ---- CPU ----

    private fun readCpuPercent(): Double {
        return try {
            val (total, idle) = readCpuSample()
            val totalDelta = total - prevCpuTotal
            val idleDelta = idle - prevCpuIdle
            prevCpuTotal = total
            prevCpuIdle = idle

            if (totalDelta > 0) {
                ((totalDelta - idleDelta).toDouble() / totalDelta * 100).coerceIn(0.0, 100.0)
            } else {
                0.0
            }
        } catch (e: Exception) {
            Log.w(TAG, "CPU read error: ${e.message}")
            0.0
        }
    }

    /** Reads /proc/stat and returns (totalJiffies, idleJiffies). */
    private fun readCpuSample(): Pair<Long, Long> {
        val reader = RandomAccessFile("/proc/stat", "r")
        val line = reader.readLine()
        reader.close()

        // cpu  user nice system idle iowait irq softirq steal
        val parts = line.split("\\s+".toRegex())
        if (parts.size < 5) return Pair(0L, 0L)

        val user = parts[1].toLongOrNull() ?: 0
        val nice = parts[2].toLongOrNull() ?: 0
        val system = parts[3].toLongOrNull() ?: 0
        val idle = parts[4].toLongOrNull() ?: 0
        val iowait = parts.getOrNull(5)?.toLongOrNull() ?: 0
        val irq = parts.getOrNull(6)?.toLongOrNull() ?: 0
        val softirq = parts.getOrNull(7)?.toLongOrNull() ?: 0
        val steal = parts.getOrNull(8)?.toLongOrNull() ?: 0

        val total = user + nice + system + idle + iowait + irq + softirq + steal
        return Pair(total, idle)
    }

    // ---- RAM ----

    private fun readRamInfo(): Pair<Long, Long> {
        return try {
            val am = context.getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
            val memInfo = ActivityManager.MemoryInfo()
            am.getMemoryInfo(memInfo)

            val totalMb = memInfo.totalMem / (1024 * 1024)
            val availMb = memInfo.availMem / (1024 * 1024)
            val usedMb = totalMb - availMb

            Pair(usedMb, totalMb)
        } catch (e: Exception) {
            Log.w(TAG, "RAM read error: ${e.message}")
            Pair(0L, 0L)
        }
    }

    // ---- Battery ----

    private data class BatteryInfo(
        val level: Int,
        val temperature: Double,
        val isCharging: Boolean
    )

    private fun readBatteryInfo(): BatteryInfo {
        return try {
            val intent = context.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
            if (intent != null) {
                val level = intent.getIntExtra(BatteryManager.EXTRA_LEVEL, -1)
                val scale = intent.getIntExtra(BatteryManager.EXTRA_SCALE, 100)
                val temp = intent.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, 0)
                val status = intent.getIntExtra(BatteryManager.EXTRA_STATUS, -1)
                val isCharging = status == BatteryManager.BATTERY_STATUS_CHARGING ||
                    status == BatteryManager.BATTERY_STATUS_FULL

                BatteryInfo(
                    level = if (scale > 0) (level * 100) / scale else level,
                    temperature = temp / 10.0,
                    isCharging = isCharging
                )
            } else {
                BatteryInfo(0, 0.0, false)
            }
        } catch (e: Exception) {
            Log.w(TAG, "Battery read error: ${e.message}")
            BatteryInfo(0, 0.0, false)
        }
    }

    // ---- Network ----

    private data class NetworkInfo(
        val type: String,
        val rxRate: Long,
        val txRate: Long
    )

    private fun readNetworkInfo(): NetworkInfo {
        val type = getNetworkType()
        val (rxRate, txRate) = calculateNetworkRates()
        return NetworkInfo(type, rxRate, txRate)
    }

    private fun getNetworkType(): String {
        return try {
            val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
            val network = cm.activeNetwork ?: return "none"
            val caps = cm.getNetworkCapabilities(network) ?: return "none"

            when {
                caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) -> "wifi"
                caps.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) -> "cellular"
                caps.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET) -> "ethernet"
                caps.hasTransport(NetworkCapabilities.TRANSPORT_VPN) -> "vpn"
                else -> "other"
            }
        } catch (e: Exception) {
            "unknown"
        }
    }

    private fun readNetworkBytes(): Pair<Long, Long> {
        val rx = TrafficStats.getTotalRxBytes()
        val tx = TrafficStats.getTotalTxBytes()
        return Pair(
            if (rx == TrafficStats.UNSUPPORTED.toLong()) 0 else rx,
            if (tx == TrafficStats.UNSUPPORTED.toLong()) 0 else tx
        )
    }

    private fun calculateNetworkRates(): Pair<Long, Long> {
        val now = System.currentTimeMillis()
        val (currentRx, currentTx) = readNetworkBytes()
        val elapsed = (now - prevNetworkTimestamp).coerceAtLeast(1)

        val rxRate = if (prevRxBytes > 0) ((currentRx - prevRxBytes) * 1000 / elapsed) else 0
        val txRate = if (prevTxBytes > 0) ((currentTx - prevTxBytes) * 1000 / elapsed) else 0

        prevRxBytes = currentRx
        prevTxBytes = currentTx
        prevNetworkTimestamp = now

        return Pair(rxRate.coerceAtLeast(0), txRate.coerceAtLeast(0))
    }
}

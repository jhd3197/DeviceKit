package com.devicekit.agent.ui

import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.fragment.app.Fragment
import com.devicekit.agent.DeviceState
import com.devicekit.agent.R

class MetricsFragment : Fragment() {

    private lateinit var cpuChart: MetricsChartView
    private lateinit var ramChart: MetricsChartView
    private lateinit var batteryValue: TextView
    private lateinit var chargingStatus: TextView
    private lateinit var tempValue: TextView
    private lateinit var tempLabel: TextView
    private lateinit var networkType: TextView
    private lateinit var networkRx: TextView
    private lateinit var networkTx: TextView

    private val handler = Handler(Looper.getMainLooper())
    private val updateRunnable = object : Runnable {
        override fun run() {
            if (isAdded) {
                updateMetrics()
                handler.postDelayed(this, 2_000)
            }
        }
    }

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View {
        return inflater.inflate(R.layout.fragment_metrics, container, false)
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        cpuChart = view.findViewById(R.id.cpuChart)
        ramChart = view.findViewById(R.id.ramChart)
        batteryValue = view.findViewById(R.id.batteryValue)
        chargingStatus = view.findViewById(R.id.chargingStatus)
        tempValue = view.findViewById(R.id.tempValue)
        tempLabel = view.findViewById(R.id.tempLabel)
        networkType = view.findViewById(R.id.networkType)
        networkRx = view.findViewById(R.id.networkRx)
        networkTx = view.findViewById(R.id.networkTx)

        cpuChart.setColor(requireContext().getColor(R.color.chart_cpu))
        cpuChart.setMaxValue(100f)
        cpuChart.setLabel("CPU %")

        ramChart.setColor(requireContext().getColor(R.color.chart_ram))
        ramChart.setLabel("RAM GB")

        // Initialize RAM chart max from first available metric
        val latest = DeviceState.latestMetrics
        if (latest != null && latest.ramTotalMb > 0) {
            ramChart.setMaxValue(latest.ramTotalMb.toFloat())
        }

        // Load history
        loadHistory()
    }

    override fun onResume() {
        super.onResume()
        handler.post(updateRunnable)
    }

    override fun onPause() {
        super.onPause()
        handler.removeCallbacks(updateRunnable)
    }

    private fun loadHistory() {
        val history = DeviceState.metricsHistory
        if (history.isNotEmpty()) {
            cpuChart.setData(history.map { it.cpuPercent.toFloat() })

            val maxRam = history.maxOf { it.ramTotalMb }.toFloat().coerceAtLeast(1f)
            ramChart.setMaxValue(maxRam)
            ramChart.setData(history.map { it.ramUsedMb.toFloat() })
        }
    }

    private fun updateMetrics() {
        if (!isAdded) return

        val metrics = DeviceState.latestMetrics ?: return

        // Charts
        cpuChart.addDataPoint(metrics.cpuPercent.toFloat())

        if (metrics.ramTotalMb > 0) {
            ramChart.setMaxValue(metrics.ramTotalMb.toFloat())
        }
        ramChart.addDataPoint(metrics.ramUsedMb.toFloat())

        // Battery
        batteryValue.text = "${metrics.batteryLevel}%"
        chargingStatus.text = if (metrics.isCharging) "Charging" else "Discharging"

        // Temperature
        tempValue.text = String.format("%.1f\u00B0C", metrics.batteryTemperature)
        tempLabel.text = when {
            metrics.batteryTemperature > 45 -> "Hot"
            metrics.batteryTemperature > 35 -> "Warm"
            else -> "Normal"
        }

        // Network
        networkType.text = metrics.networkType.replaceFirstChar { it.uppercase() }
        networkRx.text = formatBytes(metrics.networkRxRate)
        networkTx.text = formatBytes(metrics.networkTxRate)
    }

    private fun formatBytes(bytesPerSec: Long): String {
        return when {
            bytesPerSec >= 1_000_000 -> String.format("%.1f MB/s", bytesPerSec / 1_000_000.0)
            bytesPerSec >= 1_000 -> String.format("%.1f KB/s", bytesPerSec / 1_000.0)
            else -> "$bytesPerSec B/s"
        }
    }
}

package com.devicekit.agent.ui

import android.content.Intent
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.LinearLayout
import android.widget.TextView
import androidx.fragment.app.Fragment
import com.devicekit.agent.BuildConfig
import com.devicekit.agent.DeviceState
import com.devicekit.agent.R
import com.devicekit.agent.services.AccessibilityAgent
import com.devicekit.agent.services.BackgroundAgent
import com.devicekit.agent.services.NotificationAgent
import com.google.android.material.button.MaterialButton

class DashboardFragment : Fragment() {

    private lateinit var connectionDot: View
    private lateinit var connectionStatus: TextView
    private lateinit var deviceIdText: TextView
    private lateinit var serverUrlDisplay: TextView
    private lateinit var toggleButton: MaterialButton
    private lateinit var statCpu: TextView
    private lateinit var statRam: TextView
    private lateinit var statBattery: TextView
    private lateinit var statTemp: TextView
    private lateinit var liveStateText: TextView

    private val handler = Handler(Looper.getMainLooper())
    private val updateRunnable = object : Runnable {
        override fun run() {
            if (isAdded) {
                updateUI()
                handler.postDelayed(this, 1_000)
            }
        }
    }

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View {
        return inflater.inflate(R.layout.fragment_dashboard, container, false)
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        connectionDot = view.findViewById(R.id.connectionDot)
        connectionStatus = view.findViewById(R.id.connectionStatus)
        deviceIdText = view.findViewById(R.id.deviceIdText)
        serverUrlDisplay = view.findViewById(R.id.serverUrlDisplay)
        toggleButton = view.findViewById(R.id.toggleButton)
        statCpu = view.findViewById(R.id.statCpu)
        statRam = view.findViewById(R.id.statRam)
        statBattery = view.findViewById(R.id.statBattery)
        statTemp = view.findViewById(R.id.statTemp)
        liveStateText = view.findViewById(R.id.liveStateText)

        toggleButton.setOnClickListener {
            val activity = requireActivity() as? com.devicekit.agent.MainActivity ?: return@setOnClickListener
            if (BackgroundAgent.isRunning) {
                activity.stopAgent()
            } else {
                activity.startAgent()
            }
        }
    }

    override fun onResume() {
        super.onResume()
        handler.post(updateRunnable)
    }

    override fun onPause() {
        super.onPause()
        handler.removeCallbacks(updateRunnable)
    }

    private fun updateUI() {
        if (!isAdded) return

        val connected = DeviceState.isConnected
        val isRunning = BackgroundAgent.isRunning

        // Connection dot
        val dot = connectionDot.background as? GradientDrawable ?: GradientDrawable()
        dot.setColor(if (connected) Color.parseColor("#10B981") else Color.parseColor("#EF4444"))
        dot.cornerRadius = 100f
        connectionDot.background = dot

        connectionStatus.text = when {
            connected -> "Connected"
            isRunning -> "Connecting..."
            else -> "Disconnected"
        }

        deviceIdText.text = DeviceState.deviceId ?: ""
        serverUrlDisplay.text = DeviceState.serverUrl

        toggleButton.text = if (isRunning) "Stop Agent" else "Start Agent"
        toggleButton.setBackgroundColor(
            if (isRunning) Color.parseColor("#EF4444") else Color.parseColor("#6366F1")
        )

        // Quick stats
        val metrics = DeviceState.latestMetrics
        if (metrics != null) {
            statCpu.text = String.format("%.1f%%", metrics.cpuPercent)
            statRam.text = "${metrics.ramUsedMb}MB"
            statBattery.text = "${metrics.batteryLevel}%"
            statTemp.text = String.format("%.1f\u00B0", metrics.batteryTemperature)
        }

        // Service rows
        updateServiceRow(R.id.accessibilityRow, "Accessibility", AccessibilityAgent.isRunning)
        updateServiceRow(R.id.backgroundRow, "Background Agent", BackgroundAgent.isRunning)
        updateServiceRow(R.id.notificationRow, "Notifications", NotificationAgent.isRunning)

        // Live state
        liveStateText.text = DeviceState.toDisplayString()
    }

    private fun updateServiceRow(rowId: Int, name: String, active: Boolean) {
        val row = view?.findViewById<LinearLayout>(rowId) ?: return
        val dot = row.findViewById<View>(R.id.serviceDot)
        val nameView = row.findViewById<TextView>(R.id.serviceName)
        val statusView = row.findViewById<TextView>(R.id.serviceStatus)

        nameView?.text = name
        statusView?.text = if (active) "Active" else "Inactive"
        statusView?.setTextColor(
            if (active) Color.parseColor("#10B981") else Color.parseColor("#6B7280")
        )

        val dotBg = dot?.background as? GradientDrawable ?: GradientDrawable()
        dotBg.setColor(
            if (active) Color.parseColor("#10B981") else Color.parseColor("#6B7280")
        )
        dotBg.cornerRadius = 100f
        dot?.background = dotBg
    }
}

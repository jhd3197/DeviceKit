package com.devicekit.agent

import android.content.Intent
import android.content.SharedPreferences
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.devicekit.agent.services.AccessibilityAgent
import com.devicekit.agent.services.BackgroundAgent
import com.devicekit.agent.services.NotificationAgent
import com.google.android.material.button.MaterialButton

class MainActivity : AppCompatActivity() {

    private lateinit var prefs: SharedPreferences
    private lateinit var statusDot: android.view.View
    private lateinit var statusText: TextView
    private lateinit var serverUrlInput: EditText
    private lateinit var toggleButton: MaterialButton
    private lateinit var liveStateText: TextView

    private val handler = Handler(Looper.getMainLooper())
    private var isAgentRunning = false

    private val updateRunnable = object : Runnable {
        override fun run() {
            updateUI()
            handler.postDelayed(this, 1_000)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        prefs = getSharedPreferences("devicekit", MODE_PRIVATE)

        statusDot = findViewById(R.id.statusDot)
        statusText = findViewById(R.id.statusText)
        serverUrlInput = findViewById(R.id.serverUrlInput)
        toggleButton = findViewById(R.id.toggleButton)
        liveStateText = findViewById(R.id.liveStateText)

        // Restore saved server URL
        val savedUrl = prefs.getString("server_url", BuildConfig.DEVICEKIT_SERVER_URL)
        serverUrlInput.setText(savedUrl)

        toggleButton.setOnClickListener {
            if (isAgentRunning) {
                stopAgent()
            } else {
                startAgent()
            }
        }

        // Check if services need permissions
        checkPermissions()
    }

    override fun onResume() {
        super.onResume()
        handler.post(updateRunnable)
    }

    override fun onPause() {
        super.onPause()
        handler.removeCallbacks(updateRunnable)
    }

    private fun startAgent() {
        val url = serverUrlInput.text.toString().trim()
        if (url.isEmpty()) {
            serverUrlInput.error = "Enter server URL"
            return
        }

        // Save URL
        DeviceState.serverUrl = url
        prefs.edit()
            .putString("server_url", url)
            .putBoolean("auto_start", true)
            .apply()

        // Start background service
        val intent = Intent(this, BackgroundAgent::class.java).apply {
            putExtra("server_url", url)
        }
        startForegroundService(intent)

        isAgentRunning = true
        toggleButton.text = "Stop Agent"
    }

    private fun stopAgent() {
        stopService(Intent(this, BackgroundAgent::class.java))
        prefs.edit().putBoolean("auto_start", false).apply()

        isAgentRunning = false
        DeviceState.isConnected = false
        toggleButton.text = "Start Agent"
    }

    private fun updateUI() {
        isAgentRunning = BackgroundAgent.isRunning

        // Connection status
        val connected = DeviceState.isConnected
        val dot = statusDot.background as? GradientDrawable ?: GradientDrawable()
        dot.setColor(if (connected) Color.parseColor("#10B981") else Color.parseColor("#EF4444"))
        dot.cornerRadius = 100f
        statusDot.background = dot

        statusText.text = when {
            connected -> "Connected"
            isAgentRunning -> "Connecting..."
            else -> "Disconnected"
        }

        toggleButton.text = if (isAgentRunning) "Stop Agent" else "Start Agent"

        // Service rows
        updateServiceRow(R.id.accessibilityRow, "Accessibility", AccessibilityAgent.isRunning)
        updateServiceRow(R.id.backgroundRow, "Background Agent", BackgroundAgent.isRunning)
        updateServiceRow(R.id.notificationRow, "Notifications", NotificationAgent.isRunning)

        // Live state
        liveStateText.text = DeviceState.toDisplayString()
    }

    private fun updateServiceRow(rowId: Int, name: String, active: Boolean) {
        val row = findViewById<LinearLayout>(rowId) ?: return
        val dot = row.findViewById<android.view.View>(R.id.serviceDot)
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

    private fun checkPermissions() {
        // Check accessibility service
        if (!AccessibilityAgent.isRunning) {
            // User needs to enable accessibility manually
            // We can prompt but not auto-enable
        }

        // Check notification listener
        if (!NotificationAgent.isRunning) {
            // User needs to enable in Settings > Notification access
        }
    }

    /**
     * Opens accessibility settings so the user can enable our service.
     */
    fun openAccessibilitySettings() {
        startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
    }

    /**
     * Opens notification listener settings.
     */
    fun openNotificationSettings() {
        startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
    }
}

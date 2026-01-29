package com.devicekit.agent.ui

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.widget.SwitchCompat
import androidx.fragment.app.Fragment
import com.devicekit.agent.BuildConfig
import com.devicekit.agent.DeviceState
import com.devicekit.agent.R
import com.devicekit.agent.services.AccessibilityAgent
import com.devicekit.agent.services.FloatingOverlayService
import com.devicekit.agent.services.NotificationAgent

class SettingsFragment : Fragment() {

    private lateinit var serverUrlInput: EditText
    private lateinit var autoStartToggle: SwitchCompat
    private lateinit var overlayToggle: SwitchCompat
    private lateinit var accessibilityStatus: TextView
    private lateinit var notificationStatus: TextView
    private lateinit var versionText: TextView

    private val handler = Handler(Looper.getMainLooper())
    private val updateRunnable = object : Runnable {
        override fun run() {
            if (isAdded) {
                updatePermissionStatus()
                handler.postDelayed(this, 2_000)
            }
        }
    }

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View {
        return inflater.inflate(R.layout.fragment_settings, container, false)
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        serverUrlInput = view.findViewById(R.id.serverUrlInput)
        autoStartToggle = view.findViewById(R.id.autoStartToggle)
        overlayToggle = view.findViewById(R.id.overlayToggle)
        accessibilityStatus = view.findViewById(R.id.accessibilityStatus)
        notificationStatus = view.findViewById(R.id.notificationStatus)
        versionText = view.findViewById(R.id.versionText)

        val prefs = requireContext().getSharedPreferences("devicekit", Context.MODE_PRIVATE)

        // Server URL
        val savedUrl = prefs.getString("server_url", BuildConfig.DEVICEKIT_SERVER_URL)
        serverUrlInput.setText(savedUrl)
        serverUrlInput.setOnFocusChangeListener { _, hasFocus ->
            if (!hasFocus) {
                val url = serverUrlInput.text.toString().trim()
                if (url.isNotEmpty()) {
                    DeviceState.serverUrl = url
                    prefs.edit().putString("server_url", url).apply()
                }
            }
        }

        // Auto-start toggle
        autoStartToggle.isChecked = prefs.getBoolean("auto_start", false)
        autoStartToggle.setOnCheckedChangeListener { _, isChecked ->
            prefs.edit().putBoolean("auto_start", isChecked).apply()
        }

        // Overlay toggle
        overlayToggle.isChecked = FloatingOverlayService.isRunning
        overlayToggle.setOnCheckedChangeListener { _, isChecked ->
            if (isChecked) {
                if (Settings.canDrawOverlays(requireContext())) {
                    startOverlayService()
                } else {
                    overlayToggle.isChecked = false
                    requestOverlayPermission()
                }
            } else {
                stopOverlayService()
            }
        }

        // Permission shortcuts
        view.findViewById<LinearLayout>(R.id.accessibilityButton).setOnClickListener {
            startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
        }

        view.findViewById<LinearLayout>(R.id.notificationButton).setOnClickListener {
            startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
        }

        versionText.text = "DeviceKit Agent v${BuildConfig.VERSION_NAME}"
    }

    override fun onResume() {
        super.onResume()
        handler.post(updateRunnable)

        // Check if overlay permission was just granted
        if (Settings.canDrawOverlays(requireContext()) && !FloatingOverlayService.isRunning) {
            // Don't auto-enable, user can toggle it
        }
        overlayToggle.isChecked = FloatingOverlayService.isRunning
    }

    override fun onPause() {
        super.onPause()
        handler.removeCallbacks(updateRunnable)

        // Save server URL when leaving
        val url = serverUrlInput.text.toString().trim()
        if (url.isNotEmpty()) {
            DeviceState.serverUrl = url
            requireContext().getSharedPreferences("devicekit", Context.MODE_PRIVATE)
                .edit().putString("server_url", url).apply()
        }
    }

    private fun updatePermissionStatus() {
        if (!isAdded) return

        accessibilityStatus.text = if (AccessibilityAgent.isRunning) "Enabled" else "Disabled"
        accessibilityStatus.setTextColor(
            requireContext().getColor(if (AccessibilityAgent.isRunning) R.color.green else R.color.red)
        )

        notificationStatus.text = if (NotificationAgent.isRunning) "Enabled" else "Disabled"
        notificationStatus.setTextColor(
            requireContext().getColor(if (NotificationAgent.isRunning) R.color.green else R.color.red)
        )
    }

    private fun requestOverlayPermission() {
        val intent = Intent(
            Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
            Uri.parse("package:${requireContext().packageName}")
        )
        startActivity(intent)
        Toast.makeText(requireContext(), "Grant overlay permission, then toggle again", Toast.LENGTH_LONG).show()
    }

    private fun startOverlayService() {
        val intent = Intent(requireContext(), FloatingOverlayService::class.java)
        requireContext().startForegroundService(intent)
    }

    private fun stopOverlayService() {
        val intent = Intent(requireContext(), FloatingOverlayService::class.java)
        requireContext().stopService(intent)
    }
}

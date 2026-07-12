package com.devicekit.agent.ui

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.view.KeyEvent
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.view.inputmethod.EditorInfo
import android.widget.Button
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
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import java.net.Inet4Address
import java.net.NetworkInterface
import java.util.concurrent.TimeUnit

class SettingsFragment : Fragment() {

    private lateinit var serverUrlInput: EditText
    private lateinit var testConnectionButton: Button
    private lateinit var connectionStatusText: TextView
    private lateinit var adbReverseGuide: LinearLayout
    private lateinit var deviceIpText: TextView
    private lateinit var scanNetworkButton: Button
    private lateinit var scanResultText: TextView
    private lateinit var autoStartToggle: SwitchCompat
    private lateinit var overlayToggle: SwitchCompat
    private lateinit var accessibilityStatus: TextView
    private lateinit var notificationStatus: TextView
    private lateinit var versionText: TextView

    private val httpClient = OkHttpClient.Builder()
        .connectTimeout(1, TimeUnit.SECONDS)
        .readTimeout(1, TimeUnit.SECONDS)
        .build()

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
        testConnectionButton = view.findViewById(R.id.testConnectionButton)
        connectionStatusText = view.findViewById(R.id.connectionStatusText)
        adbReverseGuide = view.findViewById(R.id.adbReverseGuide)
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
                saveServerUrl(prefs)
            }
        }
        serverUrlInput.setOnEditorActionListener { _, actionId, event ->
            if (actionId == EditorInfo.IME_ACTION_DONE ||
                (event?.keyCode == KeyEvent.KEYCODE_ENTER && event.action == KeyEvent.ACTION_DOWN)) {
                saveServerUrl(prefs)
                testConnection()
                true
            } else false
        }

        // Test Connection button
        testConnectionButton.setOnClickListener {
            saveServerUrl(prefs)
            testConnection()
        }

        // Copy ADB command button
        view.findViewById<Button>(R.id.copyAdbCommandButton).setOnClickListener {
            val clipboard = requireContext().getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
            clipboard.setPrimaryClip(ClipData.newPlainText("adb command", "adb reverse tcp:7317 tcp:7317"))
            Toast.makeText(requireContext(), "Command copied", Toast.LENGTH_SHORT).show()
        }

        // Network section
        deviceIpText = view.findViewById(R.id.deviceIpText)
        scanNetworkButton = view.findViewById(R.id.scanNetworkButton)
        scanResultText = view.findViewById(R.id.scanResultText)

        deviceIpText.text = getDeviceIp() ?: "Not connected to WiFi"

        scanNetworkButton.setOnClickListener {
            scanNetwork(prefs)
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

    private fun saveServerUrl(prefs: android.content.SharedPreferences) {
        val url = serverUrlInput.text.toString().trim()
        if (url.isNotEmpty()) {
            DeviceState.serverUrl = url
            prefs.edit().putString("server_url", url).apply()
        }
    }

    private fun getDeviceIp(): String? {
        try {
            val interfaces = NetworkInterface.getNetworkInterfaces() ?: return null
            for (iface in interfaces) {
                if (iface.isLoopback || !iface.isUp) continue
                for (addr in iface.inetAddresses) {
                    if (addr is Inet4Address && !addr.isLoopbackAddress) {
                        return addr.hostAddress
                    }
                }
            }
        } catch (_: Exception) {}
        return null
    }

    private fun scanNetwork(prefs: android.content.SharedPreferences) {
        val deviceIp = getDeviceIp()
        if (deviceIp == null) {
            scanResultText.text = "No WiFi connection detected"
            return
        }

        val subnet = deviceIp.substringBeforeLast(".")
        scanNetworkButton.isEnabled = false
        scanResultText.text = "Scanning $subnet.1-254:7317..."

        CoroutineScope(Dispatchers.IO).launch {
            val semaphore = Semaphore(20)
            val found = mutableListOf<String>()

            val jobs = (1..254).map { i ->
                async {
                    semaphore.acquire()
                    try {
                        val ip = "$subnet.$i"
                        val request = Request.Builder()
                            .url("http://$ip:7317/health")
                            .build()
                        val response = httpClient.newCall(request).execute()
                        if (response.isSuccessful) {
                            synchronized(found) { found.add(ip) }
                        }
                    } catch (_: Exception) {
                    } finally {
                        semaphore.release()
                    }
                }
            }

            jobs.awaitAll()

            withContext(Dispatchers.Main) {
                if (!isAdded) return@withContext
                scanNetworkButton.isEnabled = true
                if (found.isEmpty()) {
                    scanResultText.text = "No DeviceKit server found on local network"
                } else {
                    scanResultText.text = "Found: ${found.joinToString(", ")}\nTap an IP to use it."
                    // Make tappable if only one result, auto-populate
                    if (found.size == 1) {
                        val url = "http://${found[0]}:7317"
                        serverUrlInput.setText(url)
                        saveServerUrl(prefs)
                        scanResultText.text = "Found server at ${found[0]} — URL set."
                    } else {
                        scanResultText.setOnClickListener(null)
                        // Show clickable list
                        scanResultText.text = found.joinToString("\n") { ip -> "• http://$ip:7317" }
                        scanResultText.setOnClickListener {
                            // Use first found as default
                            val url = "http://${found[0]}:7317"
                            serverUrlInput.setText(url)
                            saveServerUrl(prefs)
                            scanResultText.text = "URL set to $url"
                        }
                    }
                }
            }
        }
    }

    private fun testConnection() {
        val url = serverUrlInput.text.toString().trim()
        if (url.isEmpty()) {
            connectionStatusText.text = "Enter a URL first"
            connectionStatusText.setTextColor(requireContext().getColor(R.color.text_muted))
            return
        }

        connectionStatusText.text = "Testing..."
        connectionStatusText.setTextColor(requireContext().getColor(R.color.text_muted))
        adbReverseGuide.visibility = View.GONE

        CoroutineScope(Dispatchers.IO).launch {
            val success = try {
                val request = Request.Builder().url("$url/health").build()
                val response = httpClient.newCall(request).execute()
                response.isSuccessful
            } catch (e: Exception) {
                false
            }

            withContext(Dispatchers.Main) {
                if (!isAdded) return@withContext
                if (success) {
                    connectionStatusText.text = "Connected"
                    connectionStatusText.setTextColor(requireContext().getColor(R.color.green))
                    adbReverseGuide.visibility = View.GONE
                } else {
                    connectionStatusText.text = "Unreachable"
                    connectionStatusText.setTextColor(requireContext().getColor(R.color.red))
                    // Show ADB reverse guide if using localhost
                    val isLocalhost = url.contains("127.0.0.1") || url.contains("localhost")
                    adbReverseGuide.visibility = if (isLocalhost) View.VISIBLE else View.GONE
                }
            }
        }
    }
}

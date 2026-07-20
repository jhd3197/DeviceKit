package com.devicekit.agent.ui

import android.content.Context
import android.content.Intent
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.widget.SwitchCompat
import androidx.fragment.app.Fragment
import com.devicekit.agent.R
import com.devicekit.agent.StoragePermission
import com.devicekit.agent.services.FaroAgentService
import com.faro.protocol.FaroAgentController
import com.faro.protocol.FaroStatus
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.net.Inet4Address
import java.net.NetworkInterface

/**
 * Faro remote-control screen (both editions): enable the agent, show the
 * 6-digit pairing code, manage paired controllers and the exec/write policy.
 * State comes from polling the embedded daemon via [FaroAgentController].
 */
class FaroFragment : Fragment() {

    private lateinit var enableToggle: SwitchCompat
    private lateinit var statusDot: View
    private lateinit var statusText: TextView
    private lateinit var fingerprintText: TextView
    private lateinit var addressText: TextView
    private lateinit var deviceNameInput: EditText
    private lateinit var pairButton: Button
    private lateinit var pairingCard: LinearLayout
    private lateinit var pairingCode: TextView
    private lateinit var pairingCountdown: TextView
    private lateinit var cancelPairingButton: Button
    private lateinit var peersContainer: LinearLayout
    private lateinit var noPeersText: TextView
    private lateinit var allowExecToggle: SwitchCompat
    private lateinit var allowWriteToggle: SwitchCompat
    private lateinit var storagePrompt: LinearLayout

    private val scope = CoroutineScope(Dispatchers.Main + SupervisorJob())
    private var suppressToggles = false
    private var lastPeersKey: String? = null

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View {
        return inflater.inflate(R.layout.fragment_faro, container, false)
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        enableToggle = view.findViewById(R.id.faroEnableToggle)
        statusDot = view.findViewById(R.id.faroStatusDot)
        statusText = view.findViewById(R.id.faroStatusText)
        fingerprintText = view.findViewById(R.id.faroFingerprintText)
        addressText = view.findViewById(R.id.faroAddressText)
        deviceNameInput = view.findViewById(R.id.faroDeviceNameInput)
        pairButton = view.findViewById(R.id.faroPairButton)
        pairingCard = view.findViewById(R.id.faroPairingCard)
        pairingCode = view.findViewById(R.id.faroPairingCode)
        pairingCountdown = view.findViewById(R.id.faroPairingCountdown)
        cancelPairingButton = view.findViewById(R.id.faroCancelPairingButton)
        peersContainer = view.findViewById(R.id.faroPeersContainer)
        noPeersText = view.findViewById(R.id.faroNoPeersText)
        allowExecToggle = view.findViewById(R.id.faroAllowExecToggle)
        allowWriteToggle = view.findViewById(R.id.faroAllowWriteToggle)
        storagePrompt = view.findViewById(R.id.faroStoragePrompt)

        deviceNameInput.setText(FaroAgentController.deviceName(requireContext()))
        deviceNameInput.setOnFocusChangeListener { _, hasFocus ->
            if (!hasFocus) saveDeviceName()
        }

        enableToggle.setOnCheckedChangeListener { _, isChecked ->
            if (suppressToggles) return@setOnCheckedChangeListener
            if (isChecked) {
                if (!StoragePermission.isGranted()) {
                    enableToggle.isChecked = false
                    Toast.makeText(requireContext(), "Grant all-files access first", Toast.LENGTH_LONG).show()
                    StoragePermission.request(requireContext())
                    return@setOnCheckedChangeListener
                }
                requireContext().startForegroundService(serviceIntent())
            } else {
                requireContext().stopService(serviceIntent())
            }
        }

        pairButton.setOnClickListener {
            runAgentCall("open pairing") { FaroAgentController.openPairing(it) }
        }
        cancelPairingButton.setOnClickListener {
            runAgentCall("close pairing") { FaroAgentController.closePairing(it) }
        }

        allowExecToggle.setOnCheckedChangeListener { _, _ -> pushPolicy() }
        allowWriteToggle.setOnCheckedChangeListener { _, _ -> pushPolicy() }

        view.findViewById<Button>(R.id.faroGrantStorageButton).setOnClickListener {
            StoragePermission.request(requireContext())
        }
    }

    override fun onResume() {
        super.onResume()
        storagePrompt.visibility = if (StoragePermission.isGranted()) View.GONE else View.VISIBLE
        scope.launch {
            while (isActive) {
                refresh()
                delay(1_500)
            }
        }
    }

    override fun onPause() {
        super.onPause()
        scope.coroutineContext.cancelChildren()
    }

    override fun onDestroyView() {
        super.onDestroyView()
        scope.cancel()
    }

    private fun serviceIntent() = Intent(requireContext(), FaroAgentService::class.java)

    private fun saveDeviceName() {
        val name = deviceNameInput.text.toString()
        runAgentCall("rename device") { FaroAgentController.setDeviceName(it, name) }
    }

    private fun pushPolicy() {
        if (suppressToggles) return
        val exec = allowExecToggle.isChecked
        val write = allowWriteToggle.isChecked
        runAgentCall("update policy") { FaroAgentController.setPolicy(it, exec, write) }
    }

    /** Run a controller call off the main thread, then re-render. */
    private fun runAgentCall(what: String, call: (Context) -> FaroStatus) {
        val appContext = requireContext().applicationContext
        scope.launch {
            val status = withContext(Dispatchers.IO) { call(appContext) }
            if (!isAdded) return@launch
            status.error?.let {
                Toast.makeText(requireContext(), "Failed to $what: $it", Toast.LENGTH_LONG).show()
            }
            render(status)
        }
    }

    private suspend fun refresh() {
        val appContext = context?.applicationContext ?: return
        val status = withContext(Dispatchers.IO) { FaroAgentController.status(appContext) }
        if (isAdded) render(status)
    }

    private fun render(status: FaroStatus) {
        val active = status.running && FaroAgentService.isRunning

        suppressToggles = true
        enableToggle.isChecked = active
        allowExecToggle.isChecked = status.allowExec
        allowWriteToggle.isChecked = status.allowWrite
        suppressToggles = false

        val color = requireContext().getColor(if (active) R.color.green else R.color.red)
        val dot = statusDot.background as? GradientDrawable ?: GradientDrawable()
        dot.setColor(color)
        dot.cornerRadius = 100f
        statusDot.background = dot
        statusText.text = when {
            status.error != null -> "Error: ${status.error}"
            active -> "Active — visible as \"${status.hostname}\""
            else -> "Off"
        }

        fingerprintText.text = status.fingerprint.ifEmpty { "—" }
        val ip = deviceIp()
        addressText.text = if (ip != null) "$ip:${status.port}" else "port ${status.port} (no Wi-Fi)"

        // Pairing window
        val pairing = status.pairing
        if (pairing != null) {
            pairingCard.visibility = View.VISIBLE
            pairButton.visibility = View.GONE
            pairingCode.text = pairing.code
            val m = pairing.remainingSecs / 60
            val s = pairing.remainingSecs % 60
            pairingCountdown.text = String.format("Expires in %d:%02d", m, s)
        } else {
            pairingCard.visibility = View.GONE
            pairButton.visibility = View.VISIBLE
            pairButton.isEnabled = active
        }

        // Paired controllers (rebuild only when the set changes)
        val peersKey = status.peers.joinToString("|") { it.publicKey }
        if (peersKey != lastPeersKey) {
            lastPeersKey = peersKey
            peersContainer.removeAllViews()
            noPeersText.visibility = if (status.peers.isEmpty()) View.VISIBLE else View.GONE
            for (peer in status.peers) {
                val row = layoutInflater.inflate(R.layout.item_faro_peer, peersContainer, false)
                row.findViewById<TextView>(R.id.peerName).text = peer.name.ifEmpty { "Unnamed controller" }
                row.findViewById<TextView>(R.id.peerFingerprint).text = peer.fingerprint
                row.findViewById<Button>(R.id.peerRevokeButton).setOnClickListener {
                    lastPeersKey = null
                    runAgentCall("revoke") { FaroAgentController.revokePeer(it, peer.publicKey) }
                }
                peersContainer.addView(row)
            }
        }
    }

    private fun deviceIp(): String? {
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
}

private fun kotlin.coroutines.CoroutineContext.cancelChildren() {
    this[kotlinx.coroutines.Job]?.children?.forEach { it.cancel() }
}

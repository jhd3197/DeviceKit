package com.devicekit.agent

import android.content.Intent
import android.content.SharedPreferences
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.viewpager2.widget.ViewPager2
import com.devicekit.agent.services.BackgroundAgent
import com.devicekit.agent.ui.TabPagerAdapter
import com.google.android.material.tabs.TabLayout
import com.google.android.material.tabs.TabLayoutMediator

class MainActivity : AppCompatActivity() {

    private lateinit var prefs: SharedPreferences
    private lateinit var headerStatusDot: View
    private lateinit var headerStatusText: TextView
    private lateinit var viewPager: ViewPager2

    private val handler = Handler(Looper.getMainLooper())
    private val updateRunnable = object : Runnable {
        override fun run() {
            updateHeader()
            handler.postDelayed(this, 1_000)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        prefs = getSharedPreferences("devicekit", MODE_PRIVATE)

        headerStatusDot = findViewById(R.id.headerStatusDot)
        headerStatusText = findViewById(R.id.headerStatusText)
        viewPager = findViewById(R.id.viewPager)

        val tabLayout = findViewById<TabLayout>(R.id.tabLayout)

        // Setup ViewPager2 with adapter
        val adapter = TabPagerAdapter(this)
        viewPager.adapter = adapter

        // Connect TabLayout with ViewPager2
        TabLayoutMediator(tabLayout, viewPager) { tab, position ->
            tab.text = TabPagerAdapter.TAB_TITLES[position]
        }.attach()

        // Handle intent extras for tab navigation
        handleIntent(intent)
    }

    override fun onNewIntent(intent: Intent?) {
        super.onNewIntent(intent)
        intent?.let { handleIntent(it) }
    }

    private fun handleIntent(intent: Intent) {
        val tabIndex = intent.getIntExtra("tab_index", -1)
        if (tabIndex in 0 until TabPagerAdapter.TAB_COUNT) {
            viewPager.currentItem = tabIndex
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

    private fun updateHeader() {
        val connected = DeviceState.isConnected
        val dot = headerStatusDot.background as? GradientDrawable ?: GradientDrawable()
        dot.setColor(if (connected) Color.parseColor("#10B981") else Color.parseColor("#EF4444"))
        dot.cornerRadius = 100f
        headerStatusDot.background = dot

        headerStatusText.text = when {
            connected -> "Online"
            BackgroundAgent.isRunning -> "Connecting..."
            else -> "Offline"
        }
    }

    /**
     * Start the background agent. Called from DashboardFragment.
     */
    fun startAgent() {
        val url = prefs.getString("server_url", DeviceState.serverUrl) ?: DeviceState.serverUrl
        DeviceState.serverUrl = url
        prefs.edit()
            .putString("server_url", url)
            .putBoolean("auto_start", true)
            .apply()

        val intent = Intent(this, BackgroundAgent::class.java).apply {
            putExtra("server_url", url)
        }
        startForegroundService(intent)
        LogBuffer.log("MainActivity", "Agent started")
    }

    /**
     * Stop the background agent. Called from DashboardFragment.
     */
    fun stopAgent() {
        stopService(Intent(this, BackgroundAgent::class.java))
        prefs.edit().putBoolean("auto_start", false).apply()
        DeviceState.isConnected = false
        LogBuffer.log("MainActivity", "Agent stopped")
    }

    /**
     * Navigate to a specific tab.
     */
    fun navigateToTab(tabIndex: Int) {
        viewPager.currentItem = tabIndex
    }
}

package com.devicekit.agent

import android.content.Intent
import android.content.SharedPreferences
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.widget.FrameLayout
import android.widget.ImageButton
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.GravityCompat
import androidx.drawerlayout.widget.DrawerLayout
import androidx.fragment.app.Fragment
import androidx.fragment.app.FragmentActivity
import androidx.viewpager2.adapter.FragmentStateAdapter
import androidx.viewpager2.widget.ViewPager2
import com.devicekit.agent.services.BackgroundAgent
import com.devicekit.agent.ui.DashboardFragment
import com.devicekit.agent.ui.FaroFragment
import com.devicekit.agent.ui.FilesFragment
import com.devicekit.agent.ui.LogsFragment
import com.devicekit.agent.ui.MetricsFragment
import com.devicekit.agent.ui.SettingsFragment
import com.google.android.material.navigation.NavigationView
import com.google.android.material.tabs.TabLayout
import com.google.android.material.tabs.TabLayoutMediator

class MainActivity : AppCompatActivity() {

    private lateinit var prefs: SharedPreferences
    private lateinit var headerStatusDot: View
    private lateinit var headerStatusText: TextView
    private lateinit var drawerLayout: DrawerLayout
    private lateinit var navigationView: NavigationView
    private lateinit var toolbarTitle: TextView
    private lateinit var tabLayout: TabLayout
    private lateinit var viewPager: ViewPager2
    private lateinit var fragmentContainer: FrameLayout

    // Drawer header views
    private var navHeaderStatusDot: View? = null
    private var navHeaderStatusText: TextView? = null

    private var currentNavItemId = R.id.nav_dashboard

    private val handler = Handler(Looper.getMainLooper())
    private val updateRunnable = object : Runnable {
        override fun run() {
            updateHeader()
            handler.postDelayed(this, 1_000)
        }
    }

    companion object {
        // The 3 swipeable tabs
        private val PAGER_TITLES = arrayOf("Dashboard", "Metrics", "Logs")

        // Mapping from nav drawer IDs to pager tab indices (only for paged items)
        private val NAV_TO_PAGER = mapOf(
            R.id.nav_dashboard to 0,
            R.id.nav_metrics to 1,
            R.id.nav_logs to 2
        )
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        prefs = getSharedPreferences("devicekit", MODE_PRIVATE)

        headerStatusDot = findViewById(R.id.headerStatusDot)
        headerStatusText = findViewById(R.id.headerStatusText)
        toolbarTitle = findViewById(R.id.toolbarTitle)
        drawerLayout = findViewById(R.id.drawerLayout)
        navigationView = findViewById(R.id.navigationView)
        tabLayout = findViewById(R.id.tabLayout)
        viewPager = findViewById(R.id.viewPager)
        fragmentContainer = findViewById(R.id.fragmentContainer)

        // Get nav header views
        val headerView = navigationView.getHeaderView(0)
        navHeaderStatusDot = headerView?.findViewById(R.id.navHeaderStatusDot)
        navHeaderStatusText = headerView?.findViewById(R.id.navHeaderStatusText)

        // Setup hamburger button
        val btnHamburger = findViewById<ImageButton>(R.id.btnHamburger)
        btnHamburger.setOnClickListener {
            drawerLayout.openDrawer(GravityCompat.START)
        }

        // Setup ViewPager2 for Dashboard/Metrics/Logs
        viewPager.adapter = MainPagerAdapter(this)
        TabLayoutMediator(tabLayout, viewPager) { tab, position ->
            tab.text = PAGER_TITLES[position]
        }.attach()

        // Sync drawer checked state when pager tab changes
        viewPager.registerOnPageChangeCallback(object : ViewPager2.OnPageChangeCallback() {
            override fun onPageSelected(position: Int) {
                val navId = when (position) {
                    0 -> R.id.nav_dashboard
                    1 -> R.id.nav_metrics
                    2 -> R.id.nav_logs
                    else -> R.id.nav_dashboard
                }
                currentNavItemId = navId
                navigationView.setCheckedItem(navId)
            }
        })

        // Setup navigation drawer item selection
        navigationView.setNavigationItemSelectedListener { menuItem ->
            val id = menuItem.itemId
            if (id != currentNavItemId) {
                currentNavItemId = id
                val pagerIndex = NAV_TO_PAGER[id]
                if (pagerIndex != null) {
                    // Swipeable tab — show pager
                    showPager()
                    viewPager.setCurrentItem(pagerIndex, false)
                } else {
                    // Non-paged section — show fragment container
                    val fragment = when (id) {
                        R.id.nav_files -> FilesFragment()
                        R.id.nav_faro -> FaroFragment()
                        R.id.nav_settings -> SettingsFragment()
                        else -> return@setNavigationItemSelectedListener true
                    }
                    showFragment(fragment)
                }
            }
            drawerLayout.closeDrawer(GravityCompat.START)
            true
        }

        // Set initial state
        if (savedInstanceState == null) {
            showPager()
            navigationView.setCheckedItem(R.id.nav_dashboard)
        }

        handleIntent(intent)
    }

    override fun onNewIntent(intent: Intent?) {
        super.onNewIntent(intent)
        intent?.let { handleIntent(it) }
    }

    private fun handleIntent(intent: Intent) {
        val tabIndex = intent.getIntExtra("tab_index", -1)
        if (tabIndex < 0) return
        when (tabIndex) {
            0, 1, 2 -> {
                // Paged tabs: Dashboard=0, Metrics=1, Logs=2
                // Old mapping: 0=Dashboard, 1=Metrics, 3=Logs
                val pagerIndex = when (tabIndex) {
                    0 -> 0
                    1 -> 1
                    3 -> 2
                    else -> tabIndex.coerceAtMost(2)
                }
                showPager()
                viewPager.setCurrentItem(pagerIndex, false)
            }
            // Old tab_index 2=Files, 4=Settings — still supported
            else -> {
                val (navId, fragment) = when (tabIndex) {
                    2 -> R.id.nav_files to FilesFragment()
                    4 -> R.id.nav_settings to SettingsFragment()
                    3 -> { showPager(); viewPager.setCurrentItem(2, false); return }
                    else -> return
                }
                currentNavItemId = navId
                navigationView.setCheckedItem(navId)
                showFragment(fragment)
            }
        }
    }

    private fun showPager() {
        tabLayout.visibility = View.VISIBLE
        viewPager.visibility = View.VISIBLE
        fragmentContainer.visibility = View.GONE
        toolbarTitle.text = "DeviceKit Agent"
    }

    private fun showFragment(fragment: Fragment) {
        tabLayout.visibility = View.GONE
        viewPager.visibility = View.GONE
        fragmentContainer.visibility = View.VISIBLE
        toolbarTitle.text = when (currentNavItemId) {
            R.id.nav_files -> "Files"
            R.id.nav_faro -> "Faro Remote"
            R.id.nav_settings -> "Settings"
            else -> "DeviceKit Agent"
        }
        supportFragmentManager.beginTransaction()
            .replace(R.id.fragmentContainer, fragment)
            .commit()
    }

    override fun onResume() {
        super.onResume()
        handler.post(updateRunnable)
    }

    override fun onPause() {
        super.onPause()
        handler.removeCallbacks(updateRunnable)
    }

    @Deprecated("Use OnBackPressedDispatcher", ReplaceWith("onBackPressedDispatcher"))
    override fun onBackPressed() {
        if (drawerLayout.isDrawerOpen(GravityCompat.START)) {
            drawerLayout.closeDrawer(GravityCompat.START)
        } else if (fragmentContainer.visibility == View.VISIBLE) {
            // If in Files/Settings, go back to paged tabs
            showPager()
            currentNavItemId = R.id.nav_dashboard
            navigationView.setCheckedItem(R.id.nav_dashboard)
            viewPager.setCurrentItem(0, false)
        } else {
            super.onBackPressed()
        }
    }

    private fun updateHeader() {
        val connected = DeviceState.isConnected
        val color = if (connected) Color.parseColor("#10B981") else Color.parseColor("#EF4444")
        val statusText = when {
            connected -> "Online"
            BackgroundAgent.isRunning -> "Connecting..."
            else -> "Offline"
        }

        val dot = headerStatusDot.background as? GradientDrawable ?: GradientDrawable()
        dot.setColor(color)
        dot.cornerRadius = 100f
        headerStatusDot.background = dot
        headerStatusText.text = statusText

        navHeaderStatusDot?.let { dotView ->
            val navDot = dotView.background as? GradientDrawable ?: GradientDrawable()
            navDot.setColor(color)
            navDot.cornerRadius = 100f
            dotView.background = navDot
        }
        navHeaderStatusText?.text = statusText
    }

    fun navigateToSection(navItemId: Int) {
        val pagerIndex = NAV_TO_PAGER[navItemId]
        if (pagerIndex != null) {
            showPager()
            viewPager.setCurrentItem(pagerIndex, false)
        } else {
            val fragment = when (navItemId) {
                R.id.nav_files -> FilesFragment()
                R.id.nav_faro -> FaroFragment()
                R.id.nav_settings -> SettingsFragment()
                else -> return
            }
            currentNavItemId = navItemId
            navigationView.setCheckedItem(navItemId)
            showFragment(fragment)
        }
    }

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

    fun stopAgent() {
        stopService(Intent(this, BackgroundAgent::class.java))
        prefs.edit().putBoolean("auto_start", false).apply()
        DeviceState.isConnected = false
        LogBuffer.log("MainActivity", "Agent stopped")
    }

    // ViewPager adapter for the 3 swipeable tabs
    private class MainPagerAdapter(activity: FragmentActivity) : FragmentStateAdapter(activity) {
        override fun getItemCount(): Int = 3
        override fun createFragment(position: Int): Fragment = when (position) {
            0 -> DashboardFragment()
            1 -> MetricsFragment()
            2 -> LogsFragment()
            else -> DashboardFragment()
        }
    }
}

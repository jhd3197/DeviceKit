package com.devicekit.agent

import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import com.devicekit.agent.ui.FaroFragment

/**
 * Faro edition: a single screen — the Faro remote-control panel. The DeviceKit
 * fleet UI (dashboard, drawer, tabs) exists only in the full edition's
 * MainActivity (src/full).
 */
class MainActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_faro)

        if (savedInstanceState == null) {
            supportFragmentManager.beginTransaction()
                .replace(R.id.faroContainer, FaroFragment())
                .commit()
        }
    }

    // Shared code (DashboardFragment, compiled into both editions but never
    // shown here) targets the full edition's MainActivity API; keep the same
    // surface so both flavors compile from one src/main.
    fun startAgent() {}
    fun stopAgent() {}
    fun navigateToSection(navItemId: Int) {}
}

package com.devicekit.agent.ui

import androidx.fragment.app.Fragment
import androidx.fragment.app.FragmentActivity
import androidx.viewpager2.adapter.FragmentStateAdapter

class TabPagerAdapter(activity: FragmentActivity) : FragmentStateAdapter(activity) {

    companion object {
        const val TAB_DASHBOARD = 0
        const val TAB_METRICS = 1
        const val TAB_LOGS = 2
        const val TAB_SETTINGS = 3
        const val TAB_COUNT = 4

        val TAB_TITLES = arrayOf("Dashboard", "Metrics", "Logs", "Settings")
    }

    override fun getItemCount(): Int = TAB_COUNT

    override fun createFragment(position: Int): Fragment = when (position) {
        TAB_DASHBOARD -> DashboardFragment()
        TAB_METRICS -> MetricsFragment()
        TAB_LOGS -> LogsFragment()
        TAB_SETTINGS -> SettingsFragment()
        else -> DashboardFragment()
    }
}

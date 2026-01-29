package com.devicekit.agent.ui

import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ScrollView
import android.widget.TextView
import androidx.fragment.app.Fragment
import com.devicekit.agent.LogBuffer
import com.devicekit.agent.R
import java.text.SimpleDateFormat
import java.util.*

class LogsFragment : Fragment() {

    private lateinit var logText: TextView
    private lateinit var logScrollView: ScrollView
    private lateinit var chipAll: TextView
    private lateinit var chipEvents: TextView
    private lateinit var chipErrors: TextView
    private lateinit var chipMetrics: TextView
    private lateinit var clearButton: TextView

    private var currentFilter: LogBuffer.Level? = null // null = all
    private val dateFormat = SimpleDateFormat("HH:mm:ss", Locale.US)

    private val logListener: (LogBuffer.LogEntry) -> Unit = { entry ->
        Handler(Looper.getMainLooper()).post {
            if (isAdded) refreshLogs()
        }
    }

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View {
        return inflater.inflate(R.layout.fragment_logs, container, false)
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        logText = view.findViewById(R.id.logText)
        logScrollView = view.findViewById(R.id.logScrollView)
        chipAll = view.findViewById(R.id.chipAll)
        chipEvents = view.findViewById(R.id.chipEvents)
        chipErrors = view.findViewById(R.id.chipErrors)
        chipMetrics = view.findViewById(R.id.chipMetrics)
        clearButton = view.findViewById(R.id.clearButton)

        chipAll.setOnClickListener { setFilter(null) }
        chipEvents.setOnClickListener { setFilter(LogBuffer.Level.EVENT) }
        chipErrors.setOnClickListener { setFilter(LogBuffer.Level.ERROR) }
        chipMetrics.setOnClickListener { setFilter(LogBuffer.Level.METRICS) }

        clearButton.setOnClickListener {
            LogBuffer.clear()
            refreshLogs()
        }

        setFilter(null)
    }

    override fun onResume() {
        super.onResume()
        LogBuffer.addListener(logListener)
        refreshLogs()
    }

    override fun onPause() {
        super.onPause()
        LogBuffer.removeListener(logListener)
    }

    private fun setFilter(level: LogBuffer.Level?) {
        currentFilter = level
        chipAll.isSelected = level == null
        chipEvents.isSelected = level == LogBuffer.Level.EVENT
        chipErrors.isSelected = level == LogBuffer.Level.ERROR
        chipMetrics.isSelected = level == LogBuffer.Level.METRICS
        refreshLogs()
    }

    private fun refreshLogs() {
        if (!isAdded) return

        val entries = LogBuffer.entries.let { all ->
            if (currentFilter != null) all.filter { it.level == currentFilter } else all
        }

        if (entries.isEmpty()) {
            logText.text = "No logs yet..."
            return
        }

        val sb = StringBuilder()
        for (entry in entries) {
            val time = dateFormat.format(Date(entry.timestamp))
            val levelTag = when (entry.level) {
                LogBuffer.Level.EVENT -> "EVT"
                LogBuffer.Level.ERROR -> "ERR"
                LogBuffer.Level.METRICS -> "MET"
            }
            sb.appendLine("[$time] [$levelTag] [${entry.source}] ${entry.message}")
        }
        logText.text = sb.toString()

        // Auto-scroll to bottom
        logScrollView.post {
            logScrollView.fullScroll(View.FOCUS_DOWN)
        }
    }
}

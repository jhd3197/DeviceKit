package com.devicekit.agent.services

import android.animation.AnimatorSet
import android.animation.ObjectAnimator
import android.app.Notification
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.graphics.*
import android.graphics.drawable.GradientDrawable
import android.os.Build
import android.os.IBinder
import android.util.Log
import android.util.TypedValue
import android.view.*
import android.view.animation.OvershootInterpolator
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import androidx.core.app.NotificationCompat
import com.devicekit.agent.DeviceKitApp
import com.devicekit.agent.LogBuffer
import com.devicekit.agent.MainActivity
import com.devicekit.agent.R
import com.devicekit.agent.ui.TabPagerAdapter

class FloatingOverlayService : Service() {

    companion object {
        private const val TAG = "FloatingOverlay"
        private const val NOTIFICATION_ID = 1002

        var isRunning: Boolean = false
            private set
    }

    private lateinit var windowManager: WindowManager
    private var floatingButton: View? = null
    private var menuView: View? = null
    private var isMenuVisible = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        isRunning = true
        windowManager = getSystemService(WINDOW_SERVICE) as WindowManager
        Log.i(TAG, "FloatingOverlayService created")
        LogBuffer.log("Overlay", "Floating overlay started")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startForeground(NOTIFICATION_ID, buildNotification())
        createFloatingButton()
        return START_STICKY
    }

    private fun createFloatingButton() {
        val buttonSize = dpToPx(56)

        // Create the FAB-style button
        val button = FrameLayout(this).apply {
            val bg = GradientDrawable().apply {
                shape = GradientDrawable.OVAL
                setColor(Color.parseColor("#6366F1"))
            }
            background = bg
            elevation = dpToPx(8).toFloat()

            // DeviceKit icon - draw a simple device shape
            val iconView = View(context).apply {
                val iconSize = dpToPx(24)
                layoutParams = FrameLayout.LayoutParams(iconSize, iconSize, Gravity.CENTER)
                background = object : GradientDrawable() {
                    init {
                        shape = RECTANGLE
                        cornerRadius = dpToPx(4).toFloat()
                        setStroke(dpToPx(2), Color.WHITE)
                        setColor(Color.TRANSPARENT)
                    }
                }
            }
            addView(iconView)
        }

        val params = WindowManager.LayoutParams(
            buttonSize,
            buttonSize,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.BOTTOM or Gravity.END
            x = dpToPx(16)
            y = dpToPx(100)
        }

        // Draggable touch listener
        var initialX = 0
        var initialY = 0
        var initialTouchX = 0f
        var initialTouchY = 0f
        var isDragging = false

        button.setOnTouchListener { v, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    initialX = params.x
                    initialY = params.y
                    initialTouchX = event.rawX
                    initialTouchY = event.rawY
                    isDragging = false
                    true
                }
                MotionEvent.ACTION_MOVE -> {
                    val dx = (initialTouchX - event.rawX).toInt()
                    val dy = (initialTouchY - event.rawY).toInt()
                    if (Math.abs(dx) > 10 || Math.abs(dy) > 10) {
                        isDragging = true
                    }
                    params.x = initialX + dx
                    params.y = initialY + dy
                    windowManager.updateViewLayout(floatingButton, params)
                    true
                }
                MotionEvent.ACTION_UP -> {
                    if (!isDragging) {
                        toggleMenu()
                    }
                    true
                }
                else -> false
            }
        }

        floatingButton = button
        windowManager.addView(button, params)
    }

    private fun toggleMenu() {
        if (isMenuVisible) {
            dismissMenu()
        } else {
            showMenu()
        }
    }

    private fun showMenu() {
        if (isMenuVisible) return

        val menuLayout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            val bg = GradientDrawable().apply {
                shape = GradientDrawable.RECTANGLE
                cornerRadius = dpToPx(12).toFloat()
                setColor(Color.parseColor("#1E1B2E"))
            }
            background = bg
            elevation = dpToPx(12).toFloat()
            setPadding(dpToPx(4), dpToPx(8), dpToPx(4), dpToPx(8))
        }

        val menuItems = listOf(
            MenuAction("View Stats", "#10B981") {
                openAppAtTab(TabPagerAdapter.TAB_METRICS)
            },
            MenuAction(
                if (BackgroundAgent.isRunning) "Stop Agent" else "Start Agent",
                if (BackgroundAgent.isRunning) "#EF4444" else "#6366F1"
            ) {
                toggleAgent()
            },
            MenuAction("Toggle Logging", "#F59E0B") {
                toggleLogging()
            },
            MenuAction("Open App", "#3B82F6") {
                openAppAtTab(TabPagerAdapter.TAB_DASHBOARD)
            }
        )

        for (item in menuItems) {
            val tv = TextView(this).apply {
                text = item.title
                setTextColor(Color.parseColor(item.color))
                textSize = 14f
                setPadding(dpToPx(16), dpToPx(12), dpToPx(16), dpToPx(12))
                val itemBg = GradientDrawable().apply {
                    shape = GradientDrawable.RECTANGLE
                    cornerRadius = dpToPx(8).toFloat()
                    setColor(Color.parseColor("#2A2740"))
                }
                background = itemBg
                val lp = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT
                ).apply {
                    setMargins(dpToPx(4), dpToPx(2), dpToPx(4), dpToPx(2))
                }
                layoutParams = lp
                setOnClickListener {
                    item.action()
                    dismissMenu()
                }
            }
            menuLayout.addView(tv)
        }

        val menuParams = WindowManager.LayoutParams(
            dpToPx(180),
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.BOTTOM or Gravity.END
            x = dpToPx(16)
            y = dpToPx(170)
        }

        menuView = menuLayout
        windowManager.addView(menuLayout, menuParams)
        isMenuVisible = true

        // Slide-up animation
        menuLayout.translationY = dpToPx(40).toFloat()
        menuLayout.alpha = 0f
        val slideUp = ObjectAnimator.ofFloat(menuLayout, "translationY", 0f)
        val fadeIn = ObjectAnimator.ofFloat(menuLayout, "alpha", 1f)
        AnimatorSet().apply {
            playTogether(slideUp, fadeIn)
            duration = 200
            interpolator = OvershootInterpolator(1.2f)
            start()
        }
    }

    private fun dismissMenu() {
        if (!isMenuVisible) return
        menuView?.let {
            try {
                windowManager.removeView(it)
            } catch (e: Exception) {
                // View may already be removed
            }
        }
        menuView = null
        isMenuVisible = false
    }

    private fun openAppAtTab(tabIndex: Int) {
        val intent = Intent(this, MainActivity::class.java).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
            putExtra("tab_index", tabIndex)
        }
        startActivity(intent)
    }

    private fun toggleAgent() {
        if (BackgroundAgent.isRunning) {
            stopService(Intent(this, BackgroundAgent::class.java))
            LogBuffer.log("Overlay", "Agent stopped via overlay")
        } else {
            val prefs = getSharedPreferences("devicekit", MODE_PRIVATE)
            val url = prefs.getString("server_url", "") ?: ""
            if (url.isNotEmpty()) {
                val intent = Intent(this, BackgroundAgent::class.java).apply {
                    putExtra("server_url", url)
                }
                startForegroundService(intent)
                LogBuffer.log("Overlay", "Agent started via overlay")
            }
        }
    }

    private fun toggleLogging() {
        LogBuffer.log("Overlay", "Verbose logging toggled")
    }

    private fun buildNotification(): Notification {
        val pendingIntent = PendingIntent.getActivity(
            this, 0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        return NotificationCompat.Builder(this, DeviceKitApp.CHANNEL_ID)
            .setContentTitle("DeviceKit Overlay")
            .setContentText("Floating overlay is active")
            .setSmallIcon(R.drawable.ic_notification)
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .build()
    }

    override fun onDestroy() {
        super.onDestroy()
        isRunning = false
        dismissMenu()
        floatingButton?.let {
            try {
                windowManager.removeView(it)
            } catch (e: Exception) {
                // Already removed
            }
        }
        floatingButton = null
        Log.i(TAG, "FloatingOverlayService destroyed")
        LogBuffer.log("Overlay", "Floating overlay stopped")
    }

    private fun dpToPx(dp: Int): Int {
        return TypedValue.applyDimension(
            TypedValue.COMPLEX_UNIT_DIP,
            dp.toFloat(),
            resources.displayMetrics
        ).toInt()
    }

    private data class MenuAction(
        val title: String,
        val color: String,
        val action: () -> Unit
    )
}

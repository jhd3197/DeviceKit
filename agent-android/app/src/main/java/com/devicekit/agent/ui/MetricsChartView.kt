package com.devicekit.agent.ui

import android.content.Context
import android.graphics.*
import android.util.AttributeSet
import android.view.View
import com.devicekit.agent.R

/**
 * Custom View drawing step charts matching frontend StepChart style:
 * dark bg, grid lines at 25/50/75%, step polyline with gradient fill, glowing endpoint dot.
 */
class MetricsChartView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0
) : View(context, attrs, defStyleAttr) {

    private val data = mutableListOf<Float>()
    private var maxDataPoints = 60
    private var lineColor = context.getColor(R.color.chart_cpu)
    private var maxValue = 100f
    private var label = ""

    private val bgPaint = Paint().apply {
        color = context.getColor(R.color.chart_bg)
        style = Paint.Style.FILL
    }

    private val gridPaint = Paint().apply {
        color = context.getColor(R.color.chart_grid)
        style = Paint.Style.STROKE
        strokeWidth = 1f
        pathEffect = DashPathEffect(floatArrayOf(4f, 4f), 0f)
    }

    private val gridLabelPaint = Paint().apply {
        color = context.getColor(R.color.text_muted)
        textSize = 24f
        isAntiAlias = true
    }

    private val linePaint = Paint().apply {
        style = Paint.Style.STROKE
        strokeWidth = 3f
        isAntiAlias = true
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
    }

    private val fillPaint = Paint().apply {
        style = Paint.Style.FILL
        isAntiAlias = true
    }

    private val dotPaint = Paint().apply {
        style = Paint.Style.FILL
        isAntiAlias = true
    }

    private val glowPaint = Paint().apply {
        style = Paint.Style.FILL
        isAntiAlias = true
        maskFilter = BlurMaskFilter(12f, BlurMaskFilter.Blur.NORMAL)
    }

    private val valuePaint = Paint().apply {
        color = Color.WHITE
        textSize = 32f
        isAntiAlias = true
        typeface = Typeface.DEFAULT_BOLD
    }

    private val labelPaint = Paint().apply {
        color = context.getColor(R.color.text_muted)
        textSize = 24f
        isAntiAlias = true
    }

    private val chartPath = Path()
    private val fillPath = Path()

    fun setColor(color: Int) {
        lineColor = color
        linePaint.color = color
        dotPaint.color = color
        glowPaint.color = Color.argb(80, Color.red(color), Color.green(color), Color.blue(color))
        invalidate()
    }

    fun setMaxValue(max: Float) {
        maxValue = max
        invalidate()
    }

    fun setLabel(text: String) {
        label = text
        invalidate()
    }

    fun addDataPoint(value: Float) {
        data.add(value.coerceIn(0f, maxValue))
        while (data.size > maxDataPoints) {
            data.removeAt(0)
        }
        invalidate()
    }

    fun setData(values: List<Float>) {
        data.clear()
        data.addAll(values.map { it.coerceIn(0f, maxValue) })
        while (data.size > maxDataPoints) {
            data.removeAt(0)
        }
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)

        val w = width.toFloat()
        val h = height.toFloat()
        val padding = 16f
        val leftPadding = 48f
        val topPadding = padding
        val bottomPadding = padding
        val chartWidth = w - leftPadding - padding
        val chartHeight = h - topPadding - bottomPadding

        // Background
        canvas.drawRoundRect(0f, 0f, w, h, 24f, 24f, bgPaint)

        // Grid lines at 25%, 50%, 75%
        for (pct in listOf(0.25f, 0.50f, 0.75f)) {
            val y = topPadding + chartHeight * (1f - pct)
            canvas.drawLine(leftPadding, y, w - padding, y, gridPaint)
            val labelText = "${(maxValue * pct).toInt()}%"
            canvas.drawText(labelText, 4f, y + 8f, gridLabelPaint)
        }

        if (data.size < 2) {
            // Show empty state
            val emptyPaint = Paint(labelPaint).apply { textSize = 28f; textAlign = Paint.Align.CENTER }
            canvas.drawText("Waiting for data...", w / 2, h / 2, emptyPaint)
            return
        }

        // Build step chart path
        val stepWidth = chartWidth / (maxDataPoints - 1).toFloat()
        val startOffset = (maxDataPoints - data.size) * stepWidth

        chartPath.reset()
        fillPath.reset()

        for (i in data.indices) {
            val x = leftPadding + startOffset + i * stepWidth
            val y = topPadding + chartHeight * (1f - data[i] / maxValue)

            if (i == 0) {
                chartPath.moveTo(x, y)
                fillPath.moveTo(x, topPadding + chartHeight)
                fillPath.lineTo(x, y)
            } else {
                // Step: horizontal then vertical
                val prevX = leftPadding + startOffset + (i - 1) * stepWidth
                chartPath.lineTo(x, chartPath.let {
                    // get the previous Y by calculating it
                    topPadding + chartHeight * (1f - data[i - 1] / maxValue)
                })
                chartPath.lineTo(x, y)

                fillPath.lineTo(x, topPadding + chartHeight * (1f - data[i - 1] / maxValue))
                fillPath.lineTo(x, y)
            }
        }

        // Close fill path
        val lastX = leftPadding + startOffset + (data.size - 1) * stepWidth
        val lastY = topPadding + chartHeight * (1f - data.last() / maxValue)
        fillPath.lineTo(lastX, topPadding + chartHeight)
        fillPath.close()

        // Gradient fill
        fillPaint.shader = LinearGradient(
            0f, topPadding, 0f, topPadding + chartHeight,
            Color.argb(60, Color.red(lineColor), Color.green(lineColor), Color.blue(lineColor)),
            Color.argb(5, Color.red(lineColor), Color.green(lineColor), Color.blue(lineColor)),
            Shader.TileMode.CLAMP
        )
        canvas.drawPath(fillPath, fillPaint)

        // Line
        linePaint.color = lineColor
        canvas.drawPath(chartPath, linePaint)

        // Glowing endpoint dot
        canvas.drawCircle(lastX, lastY, 8f, glowPaint)
        canvas.drawCircle(lastX, lastY, 4f, dotPaint)

        // Current value text
        val currentValue = data.last()
        val valueStr = if (maxValue > 100) "${currentValue.toInt()}" else String.format("%.1f%%", currentValue)
        canvas.drawText(valueStr, w - padding - valuePaint.measureText(valueStr), topPadding + 32f, valuePaint)

        if (label.isNotEmpty()) {
            canvas.drawText(label, w - padding - labelPaint.measureText(label), topPadding + 56f, labelPaint)
        }
    }
}

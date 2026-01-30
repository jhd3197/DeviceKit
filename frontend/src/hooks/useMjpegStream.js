import { useEffect, useRef, useState, useCallback } from 'react'
import { api } from '../api'

const QUALITY_PRESETS = {
  low: { fps: 5, quality: 30 },
  medium: { fps: 15, quality: 50 },
  high: { fps: 30, quality: 80 },
}

export default function useMjpegStream(deviceId, { quality = 'medium', enabled = true } = {}) {
  const canvasRef = useRef(null)
  const [connected, setConnected] = useState(false)
  const [actualFps, setActualFps] = useState(0)
  const [latencyMs, setLatencyMs] = useState(0)
  const [error, setError] = useState(null)
  const [frameSize, setFrameSize] = useState({ width: 0, height: 0 })

  const abortRef = useRef(null)
  const frameTimesRef = useRef([])
  const actualFpsRef = useRef(0)
  const mountedRef = useRef(true)

  const drawFrame = useCallback((blob) => {
    const canvas = canvasRef.current
    if (!canvas) return

    const url = URL.createObjectURL(blob)
    const img = new Image()
    img.onload = () => {
      if (!mountedRef.current) {
        URL.revokeObjectURL(url)
        return
      }

      // Track frame dimensions for coordinate mapping
      if (img.width !== frameSize.width || img.height !== frameSize.height) {
        setFrameSize({ width: img.width, height: img.height })
      }

      // Size canvas to match image if needed
      if (canvas.width !== img.width || canvas.height !== img.height) {
        canvas.width = img.width
        canvas.height = img.height
      }

      const ctx = canvas.getContext('2d')
      ctx.drawImage(img, 0, 0)
      URL.revokeObjectURL(url)

      // Track FPS
      const now = performance.now()
      const times = frameTimesRef.current
      times.push(now)
      // Keep only last 30 timestamps
      while (times.length > 30) times.shift()
      if (times.length >= 2) {
        const elapsed = times[times.length - 1] - times[0]
        const fps = Math.round(((times.length - 1) / elapsed) * 1000)
        actualFpsRef.current = fps
        setActualFps(fps)
      }
    }
    img.onerror = () => {
      URL.revokeObjectURL(url)
    }
    img.src = url
  }, [frameSize.width, frameSize.height])

  useEffect(() => {
    mountedRef.current = true
    return () => { mountedRef.current = false }
  }, [])

  useEffect(() => {
    if (!deviceId || !enabled) {
      setConnected(false)
      setError(null)
      return
    }

    const preset = QUALITY_PRESETS[quality] || QUALITY_PRESETS.medium
    const url = api.streamUrl(deviceId, preset.fps, preset.quality)

    const controller = new AbortController()
    abortRef.current = controller

    let cancelled = false

    async function startStream() {
      try {
        const response = await fetch(url, {
          signal: controller.signal,
          headers: {}, // no Content-Type for stream consumption
        })

        if (!response.ok) {
          throw new Error(`Stream response ${response.status}`)
        }

        setConnected(true)
        setError(null)

        const reader = response.body.getReader()
        let buffer = new Uint8Array(0)
        const boundary = new TextEncoder().encode('--droidlink_frame')

        const startTime = performance.now()

        while (!cancelled) {
          const { done, value } = await reader.read()
          if (done) break

          // Append new data to buffer
          const newBuffer = new Uint8Array(buffer.length + value.length)
          newBuffer.set(buffer)
          newBuffer.set(value, buffer.length)
          buffer = newBuffer

          // Extract frames from multipart stream
          while (true) {
            const boundaryIndex = findBytes(buffer, boundary)
            if (boundaryIndex === -1) break

            const frameData = buffer.slice(0, boundaryIndex)
            buffer = buffer.slice(boundaryIndex + boundary.length)

            // Find the JPEG data after headers (\r\n\r\n)
            const headerEnd = findBytes(frameData, new Uint8Array([13, 10, 13, 10]))
            if (headerEnd === -1) continue

            const jpegData = frameData.slice(headerEnd + 4)
            if (jpegData.length < 100) continue

            // Measure latency from frame timestamp header if present
            const headerStr = new TextDecoder().decode(frameData.slice(0, Math.min(headerEnd, 500)))
            const tsMatch = headerStr.match(/X-Timestamp:\s*(\d+)/i)
            if (tsMatch) {
              const frameTs = parseInt(tsMatch[1], 10)
              const now = Date.now()
              if (frameTs > 0 && frameTs < now + 60000) {
                setLatencyMs(Math.max(0, now - frameTs))
              }
            } else {
              // Approximate latency from frame interval
              const elapsed = performance.now() - startTime
              if (elapsed > 1000) {
                setLatencyMs(Math.round(1000 / Math.max(1, actualFpsRef.current)))
              }
            }

            const blob = new Blob([jpegData], { type: 'image/jpeg' })
            drawFrame(blob)
          }
        }
      } catch (err) {
        if (cancelled || err.name === 'AbortError') return
        if (mountedRef.current) {
          setConnected(false)
          setError(err.message || 'Stream failed')
        }
      }
    }

    startStream()

    return () => {
      cancelled = true
      controller.abort()
      abortRef.current = null
      setConnected(false)
      frameTimesRef.current = []
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deviceId, quality, enabled, drawFrame])

  return {
    canvasRef,
    connected,
    fps: actualFps,
    latencyMs,
    error,
    frameSize,
  }
}

function findBytes(haystack, needle) {
  if (needle.length === 0) return 0
  outer:
  for (let i = 0; i <= haystack.length - needle.length; i++) {
    for (let j = 0; j < needle.length; j++) {
      if (haystack[i + j] !== needle[j]) continue outer
    }
    return i
  }
  return -1
}

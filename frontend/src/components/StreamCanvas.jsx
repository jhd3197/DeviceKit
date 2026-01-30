import React, { useState, useEffect, useRef, useCallback } from 'react'
import useMjpegStream from '../hooks/useMjpegStream'
import { api } from '../api'

const FALLBACK_POLL_MS = 1000
const STREAM_RETRY_MS = 5000

export default function StreamCanvas({
  deviceId,
  quality = 'medium',
  enabled = true,
  onMouseDown,
  onMouseMove,
  onMouseUp,
  onMouseLeave,
  onLoad,
  showLatency = true,
  showTouchOverlay = true,
  className = '',
}) {
  const { canvasRef, connected, fps, latencyMs, error, frameSize } = useMjpegStream(deviceId, {
    quality,
    enabled,
  })

  // Fallback polling state
  const [fallbackActive, setFallbackActive] = useState(false)
  const [screenTs, setScreenTs] = useState(Date.now())
  const [screenLoaded, setScreenLoaded] = useState(false)
  const fallbackImgRef = useRef(null)
  const retryTimerRef = useRef(null)
  const pollTimerRef = useRef(null)
  const hasCalledOnLoad = useRef(false)

  // Touch ripple state
  const [ripples, setRipples] = useState([])
  const rippleIdRef = useRef(0)

  // Expose canvas ref and frame size for coordinate mapping
  const containerRef = useRef(null)

  // Determine if we should fall back to polling
  useEffect(() => {
    if (!enabled) {
      setFallbackActive(false)
      return
    }
    if (error && !connected) {
      setFallbackActive(true)
    } else if (connected) {
      setFallbackActive(false)
    }
  }, [error, connected, enabled])

  // Fallback polling interval
  useEffect(() => {
    if (!fallbackActive || !deviceId) return
    const tid = setInterval(() => setScreenTs(Date.now()), FALLBACK_POLL_MS)
    pollTimerRef.current = tid
    return () => clearInterval(tid)
  }, [fallbackActive, deviceId])

  // Retry stream connection when in fallback mode
  useEffect(() => {
    if (!fallbackActive || !enabled) return
    // The hook will automatically retry when `enabled` or `quality` changes.
    // We toggle enabled briefly to trigger a reconnect attempt.
    const tid = setInterval(() => {
      // No-op: useMjpegStream handles reconnection via its own effect deps
    }, STREAM_RETRY_MS)
    retryTimerRef.current = tid
    return () => clearInterval(tid)
  }, [fallbackActive, enabled])

  // Call onLoad when first frame arrives
  useEffect(() => {
    if (connected && frameSize.width > 0 && !hasCalledOnLoad.current) {
      hasCalledOnLoad.current = true
      onLoad?.()
    }
  }, [connected, frameSize, onLoad])

  // Touch ripple effect
  const addRipple = useCallback((x, y) => {
    if (!showTouchOverlay) return
    const id = ++rippleIdRef.current
    setRipples((prev) => [...prev, { id, x, y, startTime: Date.now() }])
    setTimeout(() => {
      setRipples((prev) => prev.filter((r) => r.id !== id))
    }, 600)
  }, [showTouchOverlay])

  // Wrap mouse handlers to add ripple on mousedown
  const handleMouseDown = useCallback((e) => {
    if (showTouchOverlay) {
      const rect = e.currentTarget.getBoundingClientRect()
      addRipple(e.clientX - rect.left, e.clientY - rect.top)
    }
    onMouseDown?.(e)
  }, [onMouseDown, addRipple, showTouchOverlay])

  // Latency color
  const latencyColor = latencyMs < 100 ? '#10b981' : latencyMs < 300 ? '#eab308' : '#ef4444'

  const isStreaming = connected && !fallbackActive

  return (
    <div ref={containerRef} className={`relative w-full h-full ${className}`}>
      {/* Stream canvas (primary) */}
      <canvas
        ref={canvasRef}
        className={`w-full h-full object-cover cursor-crosshair ${isStreaming ? '' : 'hidden'}`}
        onMouseDown={handleMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={onMouseLeave}
        style={{ imageRendering: 'auto' }}
      />

      {/* Fallback polling image */}
      {fallbackActive && (
        <img
          ref={fallbackImgRef}
          src={`${api.screenshotUrl(deviceId)}?t=${screenTs}`}
          alt="Device screen"
          className={`w-full h-full object-cover cursor-crosshair ${screenLoaded ? '' : 'invisible'}`}
          onMouseDown={handleMouseDown}
          onMouseMove={onMouseMove}
          onMouseUp={onMouseUp}
          onMouseLeave={onMouseLeave}
          onError={() => setScreenLoaded(false)}
          onLoad={() => {
            setScreenLoaded(true)
            if (!hasCalledOnLoad.current) {
              hasCalledOnLoad.current = true
              onLoad?.()
            }
          }}
          draggable={false}
        />
      )}

      {/* Touch ripple overlay */}
      {showTouchOverlay && ripples.length > 0 && (
        <svg className="absolute inset-0 w-full h-full pointer-events-none z-30">
          {ripples.map((r) => (
            <circle
              key={r.id}
              cx={r.x}
              cy={r.y}
              r="20"
              fill="none"
              stroke="rgba(16,185,129,0.6)"
              strokeWidth="2"
              className="animate-ping"
              style={{ transformOrigin: `${r.x}px ${r.y}px` }}
            />
          ))}
        </svg>
      )}

      {/* Latency indicator */}
      {showLatency && isStreaming && (
        <div className="absolute top-2 right-2 flex items-center gap-1.5 bg-black/70 backdrop-blur-sm rounded px-2 py-1 z-20">
          <div
            className="w-2 h-2 rounded-full"
            style={{ backgroundColor: latencyColor }}
          />
          <span className="text-[9px] mono text-zinc-300">{latencyMs}ms</span>
          <span className="text-[9px] mono text-zinc-500">{fps}fps</span>
        </div>
      )}

      {/* Fallback/polling indicator */}
      {fallbackActive && (
        <div className="absolute top-2 right-2 flex items-center gap-1.5 bg-amber-950/80 backdrop-blur-sm rounded px-2 py-1 z-20">
          <div className="w-2 h-2 rounded-full bg-amber-500" />
          <span className="text-[9px] mono text-amber-300">POLLING</span>
        </div>
      )}

      {/* Connecting state */}
      {enabled && !connected && !fallbackActive && !error && (
        <div className="absolute inset-0 flex items-center justify-center bg-zinc-900/50 z-10">
          <span className="text-[10px] mono text-zinc-500 animate-pulse">
            CONNECTING TO STREAM...
          </span>
        </div>
      )}
    </div>
  )
}

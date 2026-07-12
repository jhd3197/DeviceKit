import { useState, useEffect, useCallback } from 'react'
import { api, subscribeToEvents } from '../api'

// Collapse per-device sparkline series into one fleet-average series, aligning devices
// from the most recent point backwards so short histories still contribute their tail.
function averageSeries(sparkMap = {}) {
  const arrays = Object.values(sparkMap).filter((a) => Array.isArray(a) && a.length >= 2)
  if (!arrays.length) return []
  const len = Math.max(...arrays.map((a) => a.length))
  const out = []
  for (let i = 0; i < len; i++) {
    const vals = arrays
      .map((a) => a[a.length - len + i])
      .filter((v) => typeof v === 'number')
    if (vals.length) out.push(vals.reduce((s, v) => s + v, 0) / vals.length)
  }
  return out
}

// Centralizes the fleet-wide data every dashboard widget shares: stats, the device list,
// fleet health, aggregate AI cost, 24h battery sparklines, and the live SSE connection.
// Extracted out of Dashboard.jsx so widgets stay self-contained while the composer owns a
// single source of truth (plan 11 phase 1). Widgets that need cross-widget state (the FQL
// bar → registry link) still lift that locally; this hook only covers the shared fleet feed.
export default function useFleetData() {
  const [stats, setStats] = useState(null)
  const [devices, setDevices] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [sseConnected, setSseConnected] = useState(false)
  const [fleetHealth, setFleetHealth] = useState(null)
  const [fleetAiCost, setFleetAiCost] = useState(0)
  const [sparklines, setSparklines] = useState({}) // device_id -> [battery %] over 24h (plan 08)
  const [trends, setTrends] = useState({ battery: [], cpu: [] }) // fleet-average 24h series
  const [toasts, setToasts] = useState([])

  const fetchData = useCallback(async () => {
    try {
      const [s, d, fh, agentStatuses] = await Promise.all([
        api.getStats(),
        api.getDevices(),
        api.getFleetHealth().catch(() => null),
        api.getAgentStatusAll().catch(() => ({})),
      ])
      setStats(s)
      setDevices(d.devices || [])
      setFleetHealth(fh)
      setError(null)

      // Aggregate AI cost from all active agents
      let totalCost = 0
      if (agentStatuses && typeof agentStatuses === 'object') {
        for (const status of Object.values(agentStatuses)) {
          if (status?.usage?.total_cost) {
            totalCost += status.usage.total_cost
          }
        }
      }
      setFleetAiCost(totalCost)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  // Initial fetch
  useEffect(() => { fetchData() }, [fetchData])

  // Battery + CPU sparklines for the fleet (24h) — cheap batch calls, refreshed
  // periodically. Per-device battery series feed the registry rows; the fleet-average
  // series feed the KPI tiles' trend lines.
  useEffect(() => {
    const loadSparks = () => {
      api.getFleetSparklines('battery_pct', null, '24h')
        .then((r) => {
          setSparklines(r.sparklines || {})
          setTrends((prev) => ({ ...prev, battery: averageSeries(r.sparklines) }))
        })
        .catch(() => {})
      api.getFleetSparklines('cpu_load', null, '24h')
        .then((r) => setTrends((prev) => ({ ...prev, cpu: averageSeries(r.sparklines) })))
        .catch(() => {})
    }
    loadSparks()
    const tid = setInterval(loadSparks, 60000)
    return () => clearInterval(tid)
  }, [])

  // SSE subscription for real-time updates
  useEffect(() => {
    const es = subscribeToEvents({
      onDeviceState: (data) => {
        setDevices(prev => prev.map(d =>
          d.device_id === data.device_id
            ? { ...d, metrics: data.state?.metrics, cpu_percent: data.state?.metrics?.cpu_percent, battery_level: data.state?.metrics?.battery_level, lastUpdate: Date.now() }
            : d
        ))
      },
      onDeviceConnected: () => {
        fetchData()
      },
      onDeviceDisconnected: (data) => {
        setDevices(prev => prev.map(d =>
          d.device_id === data.device_id ? { ...d, online: false } : d
        ))
      },
      onAlert: () => {
        setStats(prev => prev ? { ...prev, active_alerts: (prev.active_alerts || 0) + 1 } : prev)
      },
      onDeviceNew: (data) => {
        const id = `toast-${Date.now()}`
        setToasts(prev => [...prev, { id, device_id: data.device_id, info: data.info }])
        setTimeout(() => {
          setToasts(prev => prev.filter(t => t.id !== id))
        }, 15000)
      },
      onError: () => {
        setSseConnected(false)
      },
    })
    es.addEventListener('connected', () => setSseConnected(true))
    return () => es.close()
  }, [fetchData])

  const dismissToast = useCallback((id) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  return {
    stats, devices, fleetHealth, fleetAiCost, sparklines, trends, sseConnected,
    loading, error, toasts, dismissToast, refresh: fetchData,
  }
}

import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Edit2, Trash2, Bot, Smartphone } from 'lucide-react'
import { api } from '../api'

export default function Profiles() {
  const navigate = useNavigate()
  const [profiles, setProfiles] = useState([])
  const [devices, setDevices] = useState([])
  const [agentStatus, setAgentStatus] = useState({})
  const [loading, setLoading] = useState(true)

  const fetchData = async () => {
    try {
      const [pRes, dRes, aRes] = await Promise.all([
        api.getProfiles().catch(() => ({ profiles: [] })),
        api.getDevices().catch(() => ({ devices: [] })),
        api.getAgentStatusAll().catch(() => ({})),
      ])
      setProfiles(pRes.profiles || [])
      setDevices(dRes.devices || [])
      setAgentStatus(aRes || {})
    } catch {
      // silent
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
    const tid = setInterval(fetchData, 5000)
    return () => clearInterval(tid)
  }, [])

  const handleDelete = async (id) => {
    if (!confirm('Delete this profile?')) return
    try {
      await api.deleteProfile(id)
      fetchData()
    } catch {
      // silent
    }
  }

  const getDeviceName = (deviceId) => {
    const d = devices.find((dev) => dev.device_id === deviceId)
    return d?.name || deviceId
  }

  const getAgentBadge = (deviceId) => {
    const s = agentStatus[deviceId]
    if (!s || s.status === 'stopped') return null
    const colors = {
      autonomous: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
      executing_command: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
    }
    return (
      <span className={`text-[10px] px-2 py-0.5 rounded-full border ${colors[s.status] || 'bg-zinc-800 text-zinc-400 border-zinc-700'}`}>
        {s.status}
      </span>
    )
  }

  return (
    <>
      <header className="h-14 border-b border-main flex items-center justify-between px-6 bg-body shrink-0">
        <div className="flex items-center gap-3">
          <Bot className="w-5 h-5 text-zinc-400" />
          <h1 className="text-sm font-bold">AI Profiles</h1>
        </div>
        <button
          onClick={() => navigate('/profiles/new')}
          className="flex items-center gap-2 bg-white text-black px-4 py-1.5 rounded text-xs font-bold hover:bg-zinc-200 transition-all"
        >
          <Plus className="w-3 h-3" /> New Profile
        </button>
      </header>

      <div className="flex-1 p-6 overflow-y-auto">
        {loading ? (
          <div className="text-zinc-600 text-sm text-center mt-20">Loading...</div>
        ) : profiles.length === 0 ? (
          <div className="text-center mt-20">
            <Bot className="w-12 h-12 text-zinc-800 mx-auto mb-4" />
            <p className="text-zinc-500 text-sm">No profiles yet.</p>
            <button
              onClick={() => navigate('/profiles/new')}
              className="mt-4 text-xs text-white underline hover:no-underline"
            >
              Create your first profile
            </button>
          </div>
        ) : (
          <div className="bg-card-alt border border-main rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-main text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
                  <th className="text-left px-6 py-3">Name</th>
                  <th className="text-left px-6 py-3">Device</th>
                  <th className="text-left px-6 py-3">Niche</th>
                  <th className="text-left px-6 py-3">Agent</th>
                  <th className="text-right px-6 py-3">Actions</th>
                </tr>
              </thead>
              <tbody>
                {profiles.map((p) => (
                  <tr key={p.id} className="border-b border-main/50 hover:bg-zinc-900/50">
                    <td className="px-6 py-4 font-medium">{p.name}</td>
                    <td className="px-6 py-4 mono text-xs text-zinc-400 flex items-center gap-2">
                      <Smartphone className="w-3 h-3" />
                      {getDeviceName(p.device_id)}
                    </td>
                    <td className="px-6 py-4 text-zinc-400">{p.niche || '--'}</td>
                    <td className="px-6 py-4">{getAgentBadge(p.device_id)}</td>
                    <td className="px-6 py-4 text-right">
                      <button
                        onClick={() => navigate(`/profiles/${p.id}/edit`)}
                        className="p-1.5 hover:bg-zinc-800 rounded text-zinc-500 hover:text-strong mr-1"
                      >
                        <Edit2 className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => handleDelete(p.id)}
                        className="p-1.5 hover:bg-red-950 rounded text-zinc-500 hover:text-red-400"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  )
}

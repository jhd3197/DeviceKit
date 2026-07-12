// Palette frecency ranking (plan 26, ported from ServerKit's utils/paletteFrecency.js).
//
// Replaces the old "last 6 recents" list. Each palette selection is recorded per item id with a
// use count + last-used timestamp; a score blends *frequency* and *recency* with a 14-day
// exponential half-life. Items you reach for often AND recently float to the top of the empty
// palette; a one-off from last month decays toward zero. localStorage-only — cross-device sync is
// explicitly out of scope for plan 26, same as ServerKit.
//
// API:
//   recordUse(id, meta)   — bump an item on selection (meta carries label/path so recents render
//                           even when the item isn't in the live list, e.g. an offline device).
//   frecencyScore(id)     — blend-in weight for live ranking (count * decay), 0 when unseen.
//   recentEntries(n)      — top-n {id, ...meta} by frecency, for the empty-query "Recents" group.
//   recentIds(n)          — the same, ids only (kept for parity with ServerKit's surface).

const KEY = 'devicekit:palette:frecency'
const HALF_LIFE_MS = 14 * 24 * 60 * 60 * 1000 // 14 days
const MAX_ENTRIES = 200 // cap the store so a long-lived install can't grow it unbounded

function load() {
  try {
    const v = JSON.parse(localStorage.getItem(KEY))
    return v && typeof v === 'object' && !Array.isArray(v) ? v : {}
  } catch {
    return {}
  }
}

function save(store) {
  try {
    localStorage.setItem(KEY, JSON.stringify(store))
  } catch {
    /* quota / private mode — ranking simply won't persist */
  }
}

// Exponential decay factor for an age in ms: 1.0 at age 0, 0.5 after one half-life.
function decay(ageMs) {
  if (!(ageMs > 0)) return 1
  return Math.pow(0.5, ageMs / HALF_LIFE_MS)
}

// `now` is injectable for tests; defaults to wall-clock.
function scoreEntry(entry, now = Date.now()) {
  if (!entry) return 0
  const count = entry.count || 0
  const last = entry.last || 0
  return count * decay(now - last)
}

// Record a selection: increment its count, stamp `last`, and remember its render metadata.
// Trims the store to the MAX_ENTRIES highest-scoring items when it grows past the cap.
export function recordUse(id, meta = {}) {
  if (!id) return
  const store = load()
  const prev = store[id] || { count: 0, last: 0 }
  store[id] = {
    count: prev.count + 1,
    last: Date.now(),
    meta: { ...(prev.meta || {}), ...meta },
  }
  const ids = Object.keys(store)
  if (ids.length > MAX_ENTRIES) {
    const now = Date.now()
    const keep = ids
      .sort((a, b) => scoreEntry(store[b], now) - scoreEntry(store[a], now))
      .slice(0, MAX_ENTRIES)
    const trimmed = {}
    for (const k of keep) trimmed[k] = store[k]
    save(trimmed)
    return
  }
  save(store)
}

// Blend-in weight for live ranking. Higher for items used often and recently; 0 if never used.
export function frecencyScore(id, now = Date.now()) {
  if (!id) return 0
  const store = load()
  return scoreEntry(store[id], now)
}

// Top-n entries by frecency (id + remembered meta), for the empty-query "Recents" group.
export function recentEntries(n = 8) {
  const store = load()
  const now = Date.now()
  return Object.entries(store)
    .map(([id, entry]) => ({ id, score: scoreEntry(entry, now), ...(entry.meta || {}) }))
    .filter((e) => e.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, n)
}

// Ids only — parity with ServerKit's `recentIds(8)`.
export function recentIds(n = 8) {
  return recentEntries(n).map((e) => e.id)
}

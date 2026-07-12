// Headless screenshot capture for DeviceKit's README.
//
// Spins up the mock/demo Vite build (no Python backend — src/mock/ intercepts
// fetch + SSE with a fictional fleet), navigates the SPA to each route, and
// writes PNGs into docs/screenshots/. Uses an already-installed Chrome/Edge via
// puppeteer-core — no browser download.
//
//   npm run shots
//
import { spawn } from 'node:child_process'
import { setTimeout as sleep } from 'node:timers/promises'
import { existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import puppeteer from 'puppeteer-core'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const FRONTEND = path.resolve(__dirname, '..')
const OUT = path.resolve(FRONTEND, '..', 'docs', 'screenshots')
const PORT = 1425
const BASE = `http://localhost:${PORT}`

const CHROME_CANDIDATES = [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
  '/usr/bin/google-chrome',
  '/usr/bin/chromium-browser',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
]
const chrome = CHROME_CANDIDATES.find((p) => existsSync(p))
if (!chrome) {
  console.error('No Chrome/Edge found. Install one or edit CHROME_CANDIDATES.')
  process.exit(1)
}

const isWin = process.platform === 'win32'

// Compare view starts with nothing selected — drive its <select>+Add picker so
// the overlay chart is populated (Faro drives its UI the same way).
async function prepCompare(page) {
  for (const id of ['SM-A035M-01', 'Pixel-7-02', 'OP-9-03']) {
    try {
      await page.select('select', id)
      await page.evaluate(() => {
        const btn = [...document.querySelectorAll('button')].find((b) => /(^|\s)Add(\s|$)/.test(b.textContent))
        btn?.click()
      })
      await sleep(250)
    } catch {}
  }
  await sleep(500)
}

// Each shot: [filename (no ext), route, optional prep(page) fn, optional extra settle ms].
const SHOTS = [
  ['dashboard', '/'],
  ['node-detail', '/node/SM-A035M-01', null, 900], // extra settle: let the live-metrics burst fill the gauges
  ['remote-adb', '/remote-adb'],
  ['groups', '/fleet/groups'],
  ['compare', '/fleet/compare', prepCompare],
  ['monitor', '/fleet/monitor'],
  ['enrollment', '/enrollment'],
  ['command-history', '/command-history'],
  ['automations', '/automations'],
  ['automation-editor', '/automations/a1/edit'],
  ['workflow', '/automations/a1/graph'],
  ['automation-run', '/automations/runs/r9'],
  ['pipeline', '/pipeline'],
  ['jobs', '/jobs'],
  ['notifications', '/notifications'],
  ['profiles', '/profiles'],
  ['extensions', '/extensions'],
  ['settings', '/settings'],
]

async function waitForServer(url, ms = 60_000) {
  const deadline = Date.now() + ms
  while (Date.now() < deadline) {
    try {
      const r = await fetch(url)
      if (r.ok) return
    } catch {}
    await sleep(500)
  }
  throw new Error(`Vite mock server never came up at ${url}`)
}

function killTree(child) {
  if (!child || child.killed) return
  if (isWin) {
    spawn('taskkill', ['/pid', String(child.pid), '/T', '/F'], { stdio: 'ignore' })
  } else {
    try {
      process.kill(-child.pid, 'SIGKILL')
    } catch {}
  }
}

async function main() {
  console.log('› starting mock Vite server (npm run dev:mock)…')
  const server = spawn('npm', ['run', 'dev:mock'], {
    cwd: FRONTEND,
    shell: true,
    stdio: 'ignore',
    detached: !isWin,
  })

  let browser
  try {
    await waitForServer(BASE + '/')
    console.log('› server up, launching browser…')

    browser = await puppeteer.launch({
      executablePath: chrome,
      headless: true,
      defaultViewport: { width: 1440, height: 900, deviceScaleFactor: 2 },
      args: ['--force-color-profile=srgb', '--hide-scrollbars'],
    })
    const page = await browser.newPage()
    page.on('pageerror', (e) => console.warn('  page error:', e.message))

    let ok = 0
    for (const [name, route, prep, extra = 0] of SHOTS) {
      try {
        await page.goto(BASE + route, { waitUntil: 'networkidle0', timeout: 20_000 })
        await sleep(700 + extra)
        if (typeof prep === 'function') await prep(page)
        const file = path.join(OUT, `${name}.png`)
        await page.screenshot({ path: file }) // clips to the 1440×900 viewport
        console.log('  ✓', `${name}.png`)
        ok++
      } catch (e) {
        console.warn('  ✗', `${name}.png —`, e.message)
      }
    }
    console.log(`› done. Wrote ${ok}/${SHOTS.length} PNGs to docs/screenshots/`)
  } finally {
    if (browser) await browser.close()
    killTree(server)
  }
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})

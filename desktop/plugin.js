// Sochen for Hermes Desktop: a "Sochen" page in the sidebar with your Sochen desk (what waits for
// your OK, heads-ups, what's running, what finished today), a status-bar chip when something needs
// you, palette commands, and a line from your pet when a job finishes or needs you.
//
// Plain ESM, loaded uncompiled: only @hermes/plugin-sdk, react and react/jsx-runtime are imported,
// and the page talks only to this plugin's own backend (dashboard/plugin_api.py, GET /desk), which
// holds the key. Links open in the browser.

import {
  Button,
  PALETTE_AREA,
  ROUTES_AREA,
  SIDEBAR_NAV_AREA,
  STATUSBAR_AREAS,
  StatusDot,
  atom,
  host,
  useValue
} from '@hermes/plugin-sdk'
import { jsx, jsxs } from 'react/jsx-runtime'

const PATH = '/sochen'
const SETUP_URL = 'https://sochen.dev/hermes?utm_source=hermes&utm_medium=desktop'
const HOME_URL = 'https://sochen.dev/new'
const POLL_MS = 30_000

// ---- pure helpers (exported for the tests) ------------------------------------------------------

/** How many things wait for the user, and how many jobs are running. */
export function deskCounts(view) {
  if (!view || view.state !== 'ready' || !view.desk) return { needs: 0, working: 0 }
  const desk = view.desk
  return {
    needs: (desk.needs || []).length + (desk.heads_ups || []).length,
    working: (desk.working || []).length
  }
}

/** The status-bar chip's words, or null when there's nothing to say. */
export function chipLabel(view) {
  const { needs, working } = deskCounts(view)
  if (needs > 0) return `Sochen · ${needs} ${needs === 1 ? 'needs' : 'need'} you`
  if (working > 0) return `Sochen · ${working} working`
  return null
}

/** What changed between two desks, for the pet: newly finished jobs and new asks for the user's OK. */
export function deskNews(before, after) {
  if (!before || before.state !== 'ready' || !after || after.state !== 'ready') return []
  const ids = (list, key) => new Set((list || []).map(item => item[key]))
  const doneBefore = ids(before.desk.done, 'chat_id')
  const needsBefore = ids(before.desk.needs, 'chat_id')
  const news = []
  for (const item of after.desk.needs || []) {
    if (!needsBefore.has(item.chat_id)) news.push({ kind: 'needs', title: item.title })
  }
  for (const item of after.desk.done || []) {
    if (!doneBefore.has(item.chat_id)) news.push({ kind: item.stopped ? 'stopped' : 'done', title: item.title })
  }
  return news
}

/** The pet's line for one piece of news (the host caps it at 120 characters). */
export function petLine(item) {
  const title = String(item.title || 'A job').slice(0, 80)
  if (item.kind === 'needs') return `Sochen needs your OK: ${title}`
  if (item.kind === 'stopped') return `Sochen stopped: ${title}`
  return `Sochen finished: ${title}`
}

// ---- view ---------------------------------------------------------------------------------------

const muted = { color: 'var(--ui-text-tertiary)' }
const secondary = { color: 'var(--ui-text-secondary)' }

function Row({ tone, title, line, url, action, open }) {
  return jsxs('div', {
    style: { display: 'flex', alignItems: 'flex-start', gap: 10, padding: '8px 0', borderBottom: '1px solid var(--ui-stroke-secondary)' },
    children: [
      jsx(StatusDot, { tone, style: { marginTop: 6 } }),
      jsxs('div', {
        style: { flex: 1, minWidth: 0 },
        children: [
          jsx('div', { style: { fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis' }, children: title }),
          line ? jsx('div', { style: { ...muted, fontSize: 12, marginTop: 2 }, children: line }) : null
        ]
      }),
      url ? jsx(Button, { size: 'xs', variant: 'outline', onClick: () => open(url), children: action || 'Open' }) : null
    ]
  })
}

function Section({ title, items, empty }) {
  return jsxs('section', {
    style: { marginTop: 20 },
    children: [
      jsx('h2', {
        style: { ...secondary, fontSize: 11, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', margin: 0 },
        children: items.length ? `${title} · ${items.length}` : title
      }),
      items.length ? jsx('div', { children: items }) : jsx('p', { style: { ...muted, fontSize: 12, margin: '8px 0 0' }, children: empty })
    ]
  })
}

function Notice({ title, body, actions }) {
  return jsxs('div', {
    style: { marginTop: 24, maxWidth: 520 },
    children: [
      jsx('div', { style: { fontWeight: 600 }, children: title }),
      jsx('p', { style: { ...muted, fontSize: 13, lineHeight: 1.5 }, children: body }),
      jsx('div', { style: { display: 'flex', gap: 8, marginTop: 8 }, children: actions })
    ]
  })
}

function DeskPage({ store, refresh, open }) {
  const view = useValue(store)
  const desk = view.state === 'ready' ? view.desk : null
  const header = jsxs('div', {
    style: { display: 'flex', alignItems: 'center', gap: 8 },
    children: [
      jsxs('div', {
        style: { flex: 1, minWidth: 0 },
        children: [
          jsx('h1', { style: { fontSize: 18, fontWeight: 600, margin: 0 }, children: 'Sochen' }),
          jsx('div', { style: { ...muted, fontSize: 12 }, children: desk ? [desk.greeting, desk.date].filter(Boolean).join(' · ') : 'Your cloud agent, with a phone' })
        ]
      }),
      jsx(Button, { size: 'xs', variant: 'ghost', onClick: () => void refresh(), children: 'Refresh' }),
      jsx(Button, { size: 'xs', variant: 'outline', onClick: () => open(HOME_URL), children: 'Open Sochen' })
    ]
  })

  let body
  if (view.state === 'loading') {
    body = jsx('p', { style: { ...muted, marginTop: 24 }, children: 'Looking at your Sochen desk…' })
  } else if (view.state === 'setup') {
    body = jsx(Notice, {
      title: 'Connect Sochen',
      body: 'Make a key at sochen.dev/hermes (a new account’s first job is free), then add it in Settings → Plugins → Sochen → API key, or run: hermes config set SOCHEN_API_KEY <your key>. Invoices, rent receipts and bill splits work without it.',
      actions: [
        jsx(Button, { key: 'k', size: 'sm', onClick: () => open(view.setup_url || SETUP_URL), children: 'Get a key' }),
        jsx(Button, { key: 'r', size: 'sm', variant: 'outline', onClick: () => void refresh(), children: 'I’ve added it' })
      ]
    })
  } else if (view.state === 'held') {
    body = jsx(Notice, {
      title: 'Sochen needs a plan to keep going',
      body: view.message || '',
      actions: view.upgrade_url ? [jsx(Button, { key: 'p', size: 'sm', onClick: () => open(view.upgrade_url), children: 'See plans' })] : []
    })
  } else if (view.state === 'error') {
    body = jsx(Notice, {
      title: 'Couldn’t read your desk',
      body: view.error || 'Sochen didn’t answer.',
      actions: [jsx(Button, { key: 'r', size: 'sm', variant: 'outline', onClick: () => void refresh(), children: 'Try again' })]
    })
  } else {
    const needs = [
      ...(desk.needs || []).map(item =>
        jsx(Row, { key: `n-${item.chat_id}`, tone: 'warn', title: item.title, line: item.waiting_for, url: item.chat_url, action: 'Review', open })
      ),
      ...(desk.heads_ups || []).map(item => jsx(Row, { key: `h-${item.id}`, tone: 'warn', title: item.title, line: item.detail, url: null, open }))
    ]
    const working = (desk.working || []).map(item =>
      jsx(Row, { key: `w-${item.id}`, tone: 'good', title: item.title, line: item.line, url: item.chat_url, open })
    )
    const done = (desk.done || []).map(item =>
      jsx(Row, { key: `d-${item.chat_id}`, tone: item.stopped ? 'bad' : 'muted', title: item.title, line: item.line, url: item.chat_url, open })
    )
    body = jsxs('div', {
      children: [
        jsx(Section, { title: 'Needs your OK', items: needs, empty: 'When Sochen needs your OK to send, pay or book, or has a question, it waits here.' }),
        jsx(Section, { title: 'Working now', items: working, empty: 'Nothing running. Hand Sochen a job from any chat: /sochen <what you need>' }),
        jsx(Section, { title: 'Done today', items: done, empty: 'What Sochen finishes today shows here.' }),
        jsx('p', { style: { ...muted, fontSize: 12, marginTop: 24 }, children: 'Approvals happen in the Sochen app or at the chat link: Hermes can’t approve payments, bookings or messages.' })
      ]
    })
  }

  return jsxs('div', { style: { height: '100%', overflowY: 'auto', padding: '20px 24px', fontSize: 13 }, children: [header, body] })
}

function Chip({ store, go }) {
  const view = useValue(store)
  const label = chipLabel(view)
  if (!label) return null
  const { needs } = deskCounts(view)
  return jsxs('button', {
    type: 'button',
    onClick: go,
    title: 'Open your Sochen desk',
    style: { display: 'inline-flex', alignItems: 'center', gap: 6, padding: '0 6px', fontSize: 11, ...secondary, background: 'none', border: 'none', cursor: 'pointer' },
    children: [jsx(StatusDot, { tone: needs > 0 ? 'warn' : 'good' }), label]
  })
}

// ---- plugin -------------------------------------------------------------------------------------

export default {
  id: 'sochen',
  name: 'Sochen',
  register(ctx) {
    const store = atom({ state: 'loading' })
    let inFlight = false

    const open = url => {
      void Promise.resolve(ctx.os && ctx.os.openExternal ? ctx.os.openExternal(url) : false).then(opened => {
        if (!opened) host.notify({ kind: 'info', message: url })
      })
    }
    const go = () => host.navigate(PATH)

    const say = item => {
      const text = petLine(item)
      const tone = item.kind === 'needs' ? 'wait' : item.kind === 'stopped' ? 'error' : 'info'
      const petShown = ctx.pet && ctx.pet.visible && ctx.pet.visible.get()
      if (petShown) ctx.pet.say(text, { id: item.kind, tone, ttlMs: 12_000 })
      else host.notify({ kind: 'info', message: text })
    }

    const refresh = async () => {
      if (inFlight) return
      inFlight = true
      try {
        const reply = await ctx.rest('/desk', { timeoutMs: 20_000 })
        const next = reply && typeof reply === 'object' && reply.state ? reply : { state: 'error', error: 'Sochen sent an answer this page doesn’t understand.' }
        for (const item of deskNews(store.get(), next).slice(0, 3)) say(item)
        store.set(next)
      } catch (error) {
        // The backend half is off (the agent plugin isn't enabled) or the gateway is restarting.
        if (store.get().state !== 'ready') {
          store.set({ state: 'error', error: 'The Sochen plugin’s backend isn’t answering. Enable the Sochen plugin in Hermes, then try again.' })
        }
      } finally {
        inFlight = false
      }
    }

    ctx.registerMany([
      { id: 'page', area: ROUTES_AREA, data: { path: PATH }, render: () => jsx(DeskPage, { store, refresh, open }) },
      { id: 'nav', area: SIDEBAR_NAV_AREA, data: { path: PATH, label: 'Sochen', codicon: 'inbox' } },
      { id: 'chip', area: STATUSBAR_AREAS.right, order: 140, render: () => jsx(Chip, { store, go }) },
      {
        id: 'open',
        area: PALETTE_AREA,
        data: { id: 'sochen.open', label: 'Sochen: open your desk', keywords: ['sochen', 'desk', 'jobs', 'approvals'], run: go }
      },
      {
        id: 'refresh',
        area: PALETTE_AREA,
        data: { id: 'sochen.refresh', label: 'Sochen: refresh your desk', keywords: ['sochen', 'refresh'], run: () => void refresh() }
      },
      {
        id: 'web',
        area: PALETTE_AREA,
        data: { id: 'sochen.web', label: 'Sochen: open sochen.dev', keywords: ['sochen', 'web'], run: () => open(HOME_URL) }
      }
    ])

    void refresh()
    ctx.setInterval(() => void refresh(), POLL_MS)
  }
}

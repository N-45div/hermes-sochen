// desktop/plugin.js against stand-ins for the Hermes Desktop SDK: what it registers, what the pet
// says when the desk changes, and that every state of the page renders.
// Run: node --import ./tests/desktop/register.mjs --test tests/desktop/plugin.test.mjs

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { describe, it } from 'node:test'
import { host } from '@hermes/plugin-sdk'
import plugin, { chipLabel, creditsLine, deskCounts, deskNews, petLine } from '../../desktop/plugin.js'

const desk = (overrides = {}) => ({
  state: 'ready',
  desk: {
    greeting: 'Good evening, Asha',
    date: 'Saturday, November 7',
    needs: [],
    heads_ups: [],
    working: [{ id: 'ses_1', title: "Call Joe's Pizza", line: 'Eli · on a call', chat_url: 'https://sochen.dev/s/ses_1' }],
    done: [],
    ...overrides
  }
})

/** Every string in a rendered tree, joined. */
function text(node) {
  if (node == null || typeof node === 'boolean') return ''
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(text).join(' ')
  return text(node.props?.children)
}

function fakeCtx(replies) {
  const ctx = {
    registered: [],
    said: [],
    opened: [],
    intervals: [],
    rest: async path => {
      assert.equal(path, '/desk')
      const next = replies.shift()
      if (next instanceof Error) throw next
      return next
    },
    registerMany(list) {
      this.registered.push(...list)
      return () => {}
    },
    setInterval(fn, ms) {
      this.intervals.push(ms)
      return () => {}
    },
    os: { openExternal: async url => (ctx.opened.push(url), true) },
    pet: { visible: { get: () => true }, say: (line, options) => ctx.said.push({ line, ...options }) }
  }
  return ctx
}

const settle = () => new Promise(resolve => setTimeout(resolve, 0))
const page = ctx => ctx.registered.find(c => c.id === 'page')
const chip = ctx => ctx.registered.find(c => c.id === 'chip')

describe('the Sochen page in Hermes Desktop', () => {
  it('imports only what a disk plugin may', () => {
    const source = readFileSync(new URL('../../desktop/plugin.js', import.meta.url), 'utf8')
    const imports = [...source.matchAll(/from '([^']+)'/g)].map(m => m[1])
    assert.deepEqual([...new Set(imports)].sort(), ['@hermes/plugin-sdk', 'react/jsx-runtime'])
    for (const banned of ['eval(', 'new Function', 'import(', 'document.', 'window.', 'fetch(', 'localStorage']) {
      assert.ok(!source.includes(banned), banned)
    }
  })

  it('registers a page, its sidebar row, a status-bar chip and palette commands, and polls gently', async () => {
    const ctx = fakeCtx([desk()])
    plugin.register(ctx)
    await settle()
    assert.equal(plugin.id, 'sochen')
    assert.deepEqual(ctx.registered.map(c => c.area).sort(), ['palette', 'palette', 'palette', 'routes', 'sidebar.nav', 'statusBar.right'])
    assert.equal(ctx.registered.find(c => c.id === 'nav').data.path, '/sochen')
    assert.deepEqual(ctx.intervals, [30_000])
  })

  it('renders the desk, the chip, and opens links in the browser', async () => {
    const ctx = fakeCtx([desk({ needs: [{ chat_id: 'ses_9', title: 'Reply to the landlord', waiting_for: 'Okay to go ahead? Sending an email', chat_url: 'https://sochen.dev/s/ses_9' }] })])
    plugin.register(ctx)
    await settle()
    const tree = page(ctx).render()
    const words = text(tree)
    assert.match(words, /Good evening, Asha/)
    assert.match(words, /Needs your OK · 1/)
    assert.match(words, /Okay to go ahead\? Sending an email/)
    assert.match(words, /Working now · 1/)
    assert.match(text(chip(ctx).render()), /Sochen · 1 needs you/)
    const review = findButton(tree, 'Review')
    review.props.onClick()
    await settle()
    assert.deepEqual(ctx.opened, ['https://sochen.dev/s/ses_9'])
  })

  it('has the pet say when a job finishes or needs the user, but not on the first look', async () => {
    const ctx = fakeCtx([
      desk(),
      desk({
        working: [],
        done: [{ chat_id: 'ses_1', title: "Call Joe's Pizza", line: 'Eli · 8:02 PM', stopped: false, chat_url: 'https://sochen.dev/s/ses_1' }],
        needs: [{ chat_id: 'ses_9', title: 'Reply to the landlord', waiting_for: 'Okay?', chat_url: 'https://sochen.dev/s/ses_9' }]
      })
    ])
    plugin.register(ctx)
    await settle()
    assert.deepEqual(ctx.said, [])
    await clickRefresh(ctx)
    assert.deepEqual(ctx.said.map(s => [s.line, s.tone]), [
      ['Sochen needs your OK: Reply to the landlord', 'wait'],
      ["Sochen finished: Call Joe's Pizza", 'info']
    ])
  })

  it('shows how to connect when there is no key, and errors without losing the last desk', async () => {
    const ctx = fakeCtx([{ state: 'setup', setup_url: 'https://sochen.dev/hermes' }])
    plugin.register(ctx)
    await settle()
    assert.match(text(page(ctx).render()), /Connect Sochen/)
    assert.equal(chip(ctx).render(), null)

    const ctx2 = fakeCtx([desk(), new Error('gateway restarting')])
    plugin.register(ctx2)
    await settle()
    await clickRefresh(ctx2)
    assert.match(text(page(ctx2).render()), /Working now · 1/)

    const ctx3 = fakeCtx([new Error('backend off')])
    plugin.register(ctx3)
    await settle()
    assert.match(text(page(ctx3).render()), /Enable the Sochen plugin/)

    const ctx4 = fakeCtx([{ state: 'held', message: "That's your free job done.", upgrade_url: 'https://sochen.dev/pricing' }])
    plugin.register(ctx4)
    await settle()
    assert.match(text(page(ctx4).render()), /free job done/)
  })

  it('falls back to a toast when no pet is on screen', async () => {
    const ctx = fakeCtx([desk(), desk({ working: [], done: [{ chat_id: 'ses_1', title: 'Flights', line: 'Eli', stopped: true }] })])
    ctx.pet.visible.get = () => false
    plugin.register(ctx)
    await settle()
    host.notes.length = 0
    await clickRefresh(ctx)
    assert.deepEqual(host.notes.map(n => n.message), ['Sochen stopped: Flights'])
  })
})

describe('the desk in words', () => {
  it('counts and labels', () => {
    assert.deepEqual(deskCounts(desk()), { needs: 0, working: 1 })
    assert.equal(chipLabel(desk()), 'Sochen · 1 working')
    assert.equal(chipLabel(desk({ working: [] })), null)
    assert.equal(chipLabel(desk({ heads_ups: [{ id: 'h' }, { id: 'i' }] })), 'Sochen · 2 need you')
    assert.equal(chipLabel({ state: 'setup' }), null)
  })

  it('says what is left to spend', () => {
    assert.equal(creditsLine(desk({ credits: { credits_left: 63, free_start: { total: 100, used: 37, left: 63 } } })), '63 of your 100 free credits left')
    assert.equal(creditsLine(desk({ credits: { credits_left: 12345, free_start: null } })), '12,345 credits left')
    assert.equal(creditsLine(desk({ credits: { credits_left: null } })), null)
    assert.equal(creditsLine(desk()), null)
    assert.equal(creditsLine({ state: 'setup' }), null)
  })

  it('finds only what is new', () => {
    const before = desk({ done: [{ chat_id: 'a', title: 'A' }] })
    const after = desk({ done: [{ chat_id: 'a', title: 'A' }, { chat_id: 'b', title: 'B' }] })
    assert.deepEqual(deskNews(before, after), [{ kind: 'done', title: 'B' }])
    assert.deepEqual(deskNews({ state: 'loading' }, after), [])
    assert.equal(petLine({ kind: 'done', title: 'x'.repeat(200) }).length, 'Sochen finished: '.length + 80)
  })
})

function findButton(node, label) {
  if (!node || typeof node !== 'object') return null
  if (Array.isArray(node)) {
    for (const child of node) {
      const found = findButton(child, label)
      if (found) return found
    }
    return null
  }
  if (node.type === 'Button' && text(node.props.children) === label) return node
  return findButton(node.props?.children, label)
}

async function clickRefresh(ctx) {
  findButton(page(ctx).render(), 'Refresh').props.onClick()
  await settle()
  await settle()
}

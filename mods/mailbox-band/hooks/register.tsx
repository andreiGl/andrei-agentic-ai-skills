import { atom, read, update } from 'claude-code'
import type { CommandRunInput, CommandRunResult, EngineInterface, Register } from 'claude-code'

import type { MailboxSnapshot } from '../types'

type Engine = EngineInterface

const snapAtom = atom({ plugin: 'mailbox-band', key: 'snap' } as const, null)
const hiddenAtom = atom({ plugin: 'mailbox-band', key: 'hidden' } as const, false)
// The band string as last DRAWN (module-level: a render hook may not write
// $.state - drawing is pure). ui.render skips the redraw while the visible
// text is unchanged (focus-steal fix); a reload resets it, which costs at
// most one extra redraw.
let lastDrawn: string | null = null
// Bump when the snapshot shape changes: $.state survives a reload, so the
// atom can hold a pre-reload snapshot (missing new fields - the
// flags.includes crash Andrei saw) until the next refresh lands.
const SNAPSHOT_SCHEMA = 2

const mailboxDir = async ($: Engine): Promise<string> =>
  `${await $.env.get('HOME') ?? ''}/.claude/mailbox`
const scriptPath = async ($: Engine): Promise<string> =>
  `${await $.env.get('HOME') ?? ''}/.claude/scripts/claude-mail`
const REPO = 'andreiGl/claude-mailbox'

function parseConfig(text: string): { nick: string; peer: string; plainGh: boolean } {
  const nick = /^NICK=(.*)$/m.exec(text)?.[1]?.trim() ?? ''
  const peer = /^PEER=(.*)$/m.exec(text)?.[1]?.trim() ?? ''
  const plainGh = /^PLAIN_GH=1$/m.test(text)
  return { nick, peer, plainGh }
}

function parseSessions(text: string, sid8: string): { name: string; threads: string; flags: string } | null {
  for (const line of text.split('\n')) {
    // Map line: NAME:prefix:threads[:flags] - field 4 carries flags such as
    // !wake (per-session socket-wake opt-out); it is never part of threads.
    const parts = line.trim().split(':')
    const tag = parts[1]
    if (parts.length >= 3 && tag !== undefined && tag !== '' && sid8.startsWith(tag)) {
      return { name: parts[0] ?? '', threads: parts[2] ?? '', flags: parts[3] ?? '' }
    }
  }
  return null
}

function parseLive(text: string): { sid: string; socket: string }[] {
  const out: { sid: string; socket: string }[] = []
  for (const line of text.split('\n')) {
    const parts = line.trim().split(/\s+/)
    const sid = parts[0]
    const socket = parts[1]
    if (parts.length === 2 && sid !== undefined && socket !== undefined && sid !== '' && socket !== '') {
      out.push({ sid, socket })
    }
  }
  return out
}

/** The env for a gh api call: none on a PLAIN_GH lane (its only account). */
async function ghEnv($: Engine): Promise<Record<string, string>> {
  try {
    const cfg = parseConfig(await $.fs.read(`${await mailboxDir($)}/config`))
    if (cfg.plainGh) return {}
  } catch {
    // No config: fall through to the token path.
  }
  const r = await $.process.run(['gh', 'auth', 'token', '--user', 'andreiGl'], { timeoutMs: 10_000 })
  const token = r.stdout.trim()
  return r.exitCode === 0 && token !== '' ? { GH_TOKEN: token } : {}
}

/**
 * Read-only unread count for the session's threads: comments past the
 * session's cursor minus its own ids. Never calls `claude-mail check`
 * (that would consume the cursor) and never writes mailbox state.
 */
async function unreadCounts(
  $: Engine,
  mapped: { name: string; threads: string; flags: string },
): Promise<{ unread: { thread: string; count: number }[]; error: boolean }> {
  const dir = await mailboxDir($)
  let cursor = 0
  try {
    const state = await $.fs.read(`${dir}/state.${mapped.name}`)
    cursor = Number(/^last_seen_comment_id=(\d+)$/m.exec(state)?.[1] ?? 0)
  } catch {
    // No per-session state yet: fall back to the daemon cursor so the count
    // reflects what a first consumption would actually deliver.
    try {
      const daemonState = await $.fs.read(`${dir}/state.daemon`)
      cursor = Number(/^last_seen_comment_id=(\d+)$/m.exec(daemonState)?.[1] ?? 0)
    } catch {
      cursor = 0
    }
  }
  let own = new Set<number>()
  try {
    const shared = await $.fs.read(`${dir}/state.shared`)
    const raw = /^own_ids=(.*)$/m.exec(shared)?.[1] ?? ''
    own = new Set(raw.split(/\s+/).filter(x => x !== '').map(Number))
  } catch {
    own = new Set()
  }
  // `since=` wants a timestamp, not an id; 24h back keeps the fetch small
  // while comment ids only ever grow.
  const since = new Date(Date.now() - 24 * 3600 * 1000).toISOString()
  const env = await ghEnv($)
  const r = await $.process.run(
    // desc: the unread are the NEWEST comments; asc page 1 is the oldest
    // 100 of the window, which misses exactly them on busy days (home's
    // finding, same class as the receipts pagination bug).
    ['gh', 'api', `repos/${REPO}/issues/comments?sort=created&direction=desc&per_page=100&since=${since}`],
    { timeoutMs: 20_000, env },
  )
  if (r.exitCode !== 0) return { unread: [], error: true }
  try {
    const comments = JSON.parse(r.stdout) as { id: number; issue_url: string }[]
    const counts = new Map<string, number>()
    for (const c of comments) {
      if (c.id <= cursor || own.has(c.id)) continue
      const num = c.issue_url.split('/').pop() ?? ''
      if (num === '' || !mapped.threads.split(',').includes(num)) continue
      counts.set(num, (counts.get(num) ?? 0) + 1)
    }
    const unread = mapped.threads.split(',').map(t => ({ thread: t, count: counts.get(t) ?? 0 }))
    return { unread, error: false }
  } catch {
    return { unread: [], error: true }
  }
}

async function snapshot($: Engine, sid8: string): Promise<MailboxSnapshot> {
  const dir = await mailboxDir($)
  const out: MailboxSnapshot = {
    schema: SNAPSHOT_SCHEMA,
    installed: false,
    nick: '',
    peer: '',
    mapped: null,
    live: [],
    sid8,
    liveRegistered: false,
    daemon: { running: false, pid: null },
    lagSeconds: null,
    responderActive: false,
    unread: [],
    unreadError: false,
  }
  try {
    out.installed = await $.fs.exists(await scriptPath($))
  } catch {
    out.installed = false
  }
  if (!out.installed) return out
  try {
    const cfg = parseConfig(await $.fs.read(`${dir}/config`))
    out.nick = cfg.nick
    out.peer = cfg.peer
    out.mapped = parseSessions(await $.fs.read(`${dir}/sessions`), sid8)
  } catch {
    // No config or map yet: stay unmapped.
  }
  try {
    out.live = parseLive(await $.fs.read(`${dir}/live-sessions`))
    out.liveRegistered = out.live.some(l => l.sid.startsWith(sid8))
  } catch {
    out.live = []
  }
  const pgrep = await $.process.run(['pgrep', '-f', 'claude-mail daemon'], { timeoutMs: 5_000 })
  if (pgrep.exitCode === 0 && pgrep.stdout.trim() !== '') {
    out.daemon = { running: true, pid: pgrep.stdout.trim().split('\n')[0] ?? null }
  }
  try {
    const daemonState = await $.fs.read(`${dir}/state.daemon`)
    const at = /^last_seen_created_at=(.+)$/m.exec(daemonState)?.[1]
    if (at !== undefined && at !== '') {
      out.lagSeconds = Math.round((Date.now() - Date.parse(at)) / 1000)
    }
  } catch {
    out.lagSeconds = null
  }
  try {
    out.responderActive = await $.fs.exists(`${dir}/responder.active`)
  } catch {
    out.responderActive = false
  }
  if (out.mapped !== null && out.daemon.running) {
    const u = await unreadCounts($, out.mapped)
    out.unread = u.unread
    out.unreadError = u.error
  }
  return out
}

function formatStatus(snap: MailboxSnapshot): string {
  if (!snap.installed) return 'mailbox: ~/.claude/scripts/claude-mail not found on this machine.'
  const lines: string[] = []
  lines.push(`lane: ${snap.nick} (peer: ${snap.peer})`)
  lines.push(
    snap.mapped !== null
      ? `this session: ${snap.nick}/${snap.mapped.name}, thread(s) ${snap.mapped.threads}${snap.mapped.flags ? `, flags ${snap.mapped.flags}` : ''}${snap.liveRegistered ? '' : '  [NOT live-registered: the SessionStart hook did not fire]'}`
      : `this session: unmapped (sends stay lane-only ${snap.nick}; directed mail cannot reach it). Wire with /mailbox-wire <name> <threads>`,
  )
  lines.push(`daemon: ${snap.daemon.running ? `running (pid ${snap.daemon.pid ?? '?'})` : 'NOT RUNNING'}${snap.lagSeconds !== null ? `, cursor lag ${Math.round(snap.lagSeconds / 60)}m` : ''}`)
  lines.push(`responder: ${snap.responderActive ? 'turn in flight' : 'idle'}`)
  lines.push(`live sessions on this machine: ${snap.live.length}${snap.live.length > 0 ? ` (${snap.live.map(l => l.sid.slice(0, 8)).join(', ')})` : ''}`)
  if (snap.mapped !== null) {
    if (snap.unreadError) {
      lines.push('unread: unavailable (fetch failed)')
    } else {
      const parts = snap.unread.map(u => `#${u.thread}: ${u.count}`)
      lines.push(`unread (read-only count): ${parts.length > 0 ? parts.join(', ') : 'none'} - consume with claude-mail check or wait for the daemon wake`)
    }
  }
  lines.push('reminder: never run `claude-mail check` to browse - it consumes this session\'s cursor. Read with `claude-mail read <thread> --tail 30`.')
  return lines.join('\n')
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const sid = await $.session.id()
    const sid8 = sid.slice(0, 8)
    // Awaited here (home's review): the first prompt must find the snapshot
    // ready, else its briefing block is skipped. Turn completion stays
    // background - that is the hot path.
    const snap = await snapshot($, sid8)
    await update($, snapAtom, () => snap)
    await $.command.register({ name: 'mailbox', description: 'Show mailbox state: mapping, daemon, unread (read-only).' })
    await $.command.register({
      name: 'mailbox-wire',
      description: 'Map this session to mailbox thread(s): adds NAME:prefix:threads to the sessions map.',
      argumentHint: '<name> <threads>',
    })
    return next(e)
  })

  on('turn.complete', async ($, e, next) => {
    if (e.agentId !== undefined) return (await next(e)) ?? { text: '' }
    const sid = await $.session.id()
    const sid8 = sid.slice(0, 8)
    // Background refresh (home's finding): the turn must not wait on
    // pgrep + the GitHub fetch; the atom updates when the snapshot lands.
    void (async () => {
      const snap = await snapshot($, sid8)
      await update($, snapAtom, () => snap)
    })().catch(() => {})
    return (await next(e)) ?? { text: '' }
  })

  on('prompt.context', async ($, e, next) => {
    const snap = await read($, snapAtom)
    // Unmapped sessions get no block (Andrei's call, home's finding 3):
    // in unrelated projects the "not mapped" text is pure noise. The band,
    // /mailbox and /mailbox-wire still work there.
    if (snap === null || !snap.installed || snap.mapped === null) return next(e)
    // A pre-reload snapshot (schema 1) lacks flags; skip until refreshed.
    if ((snap as { schema?: number }).schema !== SNAPSHOT_SCHEMA) return next(e)
    const lines: string[] = [
      '## Mailbox (inter-Claude lane mail)',
      `Lane nick: ${snap.nick} (peer: ${snap.peer}). Script: ~/.claude/scripts/claude-mail. For the full briefing read BRIEFING.md in the ${REPO} repo before acting on mailbox mail.`,
    ]
    lines.push(`This session is mapped as ${snap.nick}/${snap.mapped.name} on thread(s) ${snap.mapped.threads}; its sends carry from=${snap.nick}/${snap.mapped.name}.${snap.mapped.flags?.includes('!wake') ? ' This session is !wake: no socket wakes; check for mail at session start, on the band, or on request.' : ''}`)
    if (snap.unreadError) {
      lines.push('Unread count unavailable (fetch failed).')
    } else {
      const total = snap.unread.reduce((a, u) => a + u.count, 0)
      if (total > 0) {
        const parts = snap.unread.filter(u => u.count > 0).map(u => `#${u.thread} x${u.count}`)
        lines.push(`Unread on your threads: ${parts.join(', ')}. Read with claude-mail read <thread> --tail 30 when asked or when a wake arrives; NEVER claude-mail check to browse - it consumes this session's cursor.`)
      }
    }
    const mine = { name: 'mailbox', text: lines.join('\n') }
    const blocks = [...(e.blocks ?? []).filter(b => b.name !== 'mailbox'), mine]
    return next({ ...e, blocks })
  })

  on('command.run', async ($, e, next) => {
    try {
      return await runCommand($, e, next)
    } catch (err) {
      return { text: `mailbox-band: command failed: ${err instanceof Error ? err.message : String(err)}` }
    }
  }).catch(($, _e, next) => {
    // The hook body already converts throws to output text; this catches a
    // failure of that conversion itself.
    return next(_e)
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const snap = await read($, snapAtom)
    const hidden = await read($, hiddenAtom)
    if (snap === null || !snap.installed || hidden) return next(e)
    // A pre-reload snapshot (schema 1) lacks flags; pass through until the
    // background refresh replaces it (session.start / turn.complete).
    if ((snap as { schema?: number }).schema !== SNAPSHOT_SCHEMA) return next(e)

    const who = snap.mapped !== null
      ? `${snap.nick}/${snap.mapped.name}${snap.mapped.flags?.includes('!wake') ? ' (no-wake)' : ''}`
      : `${snap.nick} (unmapped)`
    const daemon = snap.daemon.running
      ? `ok${snap.lagSeconds !== null ? ` · lag ${Math.round(snap.lagSeconds / 60)}m` : ''}`
      : 'DOWN'
    const unread = snap.unreadError ? '?' : String(snap.unread.reduce((a, u) => a + u.count, 0))
    const unreadPart = snap.mapped !== null ? ` · unread ${unread}` : ''
    const responder = snap.responderActive ? ' · responder busy' : ''
    const visible = `MB ${who} · daemon ${daemon}${unreadPart}${responder}`

    // Redraw only on genuine change (Andrei's focus-steal fix): a render
    // event with an identical band redraws the prompt area under the
    // user's typing - the background snapshot refresh lands ~a minute
    // after every turn.
    if (lastDrawn === visible) return next(e)
    lastDrawn = visible

    const { Box, Button, Text } = $.ui.resolve(e)

    return (
      <Box>
        <Text dimColor>
          MB {who} · daemon {daemon}{unreadPart}{responder}{' '}
        </Text>
        {snap.mapped === null && (
          <Button
            key="wire"
            label="Wire…"
            onPress={() => {
              void (async () => {
                // Issue numbers are per-repo sequential, so newest + 1
                // predicts the next thread; the user edits before Enter and
                // the real number lands only on creation.
                const env = await ghEnv($)
                const r = await $.process.run(
                  ['gh', 'api', `repos/${REPO}/issues?state=all&per_page=1`],
                  { timeoutMs: 15_000, env },
                )
                let text = '/mailbox-wire '
                if (r.exitCode === 0) {
                  try {
                    const newest = JSON.parse(r.stdout) as { number: number }[]
                    if (newest.length > 0 && newest[0] !== undefined) {
                      text = `/mailbox-wire <name> ${newest[0].number + 1}`
                    }
                  } catch {
                    // Keep the bare prefix.
                  }
                }
                await $.prompt.fill({ text, mode: 'insert' })
              })().catch(() => {})
            }}
          />
        )}
        {snap.mapped !== null && (
          <Button
            key="fetch"
            label="Fetch"
            onPress={() => {
              void (async () => {
                // The script's own envelope to THIS session's socket: the
                // turn it starts consumes the session's cursor - the same
                // path a daemon wake takes, user-triggered. The sid is
                // passed explicitly (home's review: a spawned process may
                // not inherit CLAUDE_CODE_SESSION_ID). Read-only contract
                // intact: the mod itself never checks or sends.
                const sid = await $.session.id()
                const r = await $.process.run(
                  [await scriptPath($), 'fetch', '--session', sid],
                  // 30s: the script's peek allows 20s; the button must
                  // outlive it so the fail-open path can still post.
                  { timeoutMs: 30_000 },
                )
                await $.ui.toast(r.exitCode === 0 && r.stdout.includes('no new mail') ? 'mailbox: no new mail' : r.exitCode === 0 ? 'mailbox: fetch posted - the turn starts now' : `mailbox: fetch failed - ${r.stderr.trim() || r.stdout.trim() || `exit ${r.exitCode}`}`)
                const snap2 = await snapshot($, sid.slice(0, 8))
                await update($, snapAtom, () => snap2)
              })().catch(() => {})
            }}
          />
        )}
        <Button key="hide" label="Hide" onPress={() => {
          lastDrawn = null   // the band must redraw when it comes back
          void update($, hiddenAtom, () => true).catch(() => {})
        }} />
      </Box>
    )
  })
}

async function runCommand(
  $: Engine,
  e: CommandRunInput,
  next: (e: CommandRunInput) => Promise<CommandRunResult>,
): Promise<CommandRunResult> {
  if (e.command === 'mailbox') {
    const sid = await $.session.id()
    const snap = await snapshot($, sid.slice(0, 8))
    await update($, snapAtom, () => snap)
    return { text: formatStatus(snap) }
  }
  if (e.command === 'mailbox-wire') {
    const sid = await $.session.id()
    const sid8 = sid.slice(0, 8)
    const args = e.args.trim().split(/\s+/)
    const name = args[0] ?? ''
    const threads = args[1] ?? ''
    if (name === '' || threads === '' || !/^[a-z][a-z0-9-]*$/.test(name) || !/^[0-9,]+$/.test(threads)) {
      return { text: 'usage: /mailbox-wire <name> <threads>   (name: lowercase letters/digits/-; threads: comma-separated numbers, e.g. 5 or 3,5)' }
    }
    // The thread must exist before the map names it (a typo otherwise maps a
    // session to mail that can never arrive). Read-only check.
    const env = await ghEnv($)
    const check = await $.process.run(
      ['gh', 'api', `repos/${REPO}/issues/${threads.split(',')[0]}`],
      { timeoutMs: 15_000, env },
    )
    if (check.exitCode !== 0) {
      return { text: `no thread #${threads.split(',')[0]} found on ${REPO} - open it first with: claude-mail new "<topic>"` }
    }
    const mapPath = `${await mailboxDir($)}/sessions`
    let map = ''
    try {
      map = await $.fs.read(mapPath)
    } catch {
      return { text: `mailbox: ${mapPath} not found - is the mailbox installed on this machine?` }
    }
    const existing = parseSessions(map, sid8)
    // A re-wire keeps the line's existing flags (field 4): /mailbox-wire
    // never silently turns a !wake session back into a wake target.
    const flags = existing?.flags ?? ''
    const line = flags !== '' ? `${name}:${sid8}:${threads}:${flags}` : `${name}:${sid8}:${threads}`
    if (existing !== null && existing.name === name && existing.threads === threads) {
      return { text: `already mapped: ${line} - nothing to do.` }
    }
    const kept = map
      .split('\n')
      .filter(line => {
        const p = line.trim().split(':')
        const tag = p[1]
        return !(p.length >= 3 && tag !== undefined && tag !== '' && sid8.startsWith(tag))
      })
      .join('\n')
    await $.fs.write(mapPath, `${kept.replace(/\n*$/, '\n')}${line}\n`)
    const verify = parseSessions(await $.fs.read(mapPath), sid8)
    if (verify === null || verify.name !== name || verify.threads !== threads || verify.flags !== flags) {
      return { text: 'wire FAILED: the map line did not resolve after the write - inspect ~/.claude/mailbox/sessions by hand.' }
    }
    const snap = await snapshot($, sid8)
    await update($, snapAtom, () => snap)
    const peerPost = `claude-mail send --thread ${threads.split(',')[0]} --text "session pair setup: ${snap.nick}/${name} is mapped to thread(s) ${threads} on this lane (session prefix ${sid8}). Peer half: start the peer session, then add to ~/.claude/mailbox/sessions on your machine: <peer-name>:<its 8-char sid prefix>:${threads} - the id comes from its live-sessions file after it registers. Confirm on this thread when done."`
    return {
      text: [
        `wired: ${name}:${sid8}:${threads} (map line resolves).`,
        '',
        'Peer half - post this yourself (it travels as mailbox mail):',
        peerPost,
      ].join('\n'),
    }
  }
  return next(e)
}

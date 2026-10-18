import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { SessionRecord, Step } from '../types'
import {
  CHOICES,
  applyTaskUpdate,
  applyTodoWrite,
  applyUpdatePlan,
  currentStep,
  denyReason,
  describe,
  firstLine,
  formatAgo,
  isStale,
  liveOthers,
  newRecord,
  parseRecord,
  projectKey,
  recentEditBy,
  recordEdit,
  shortPath,
  shouldAsk,
  workState,
} from './logic'

const self = atom({ plugin: 'collision-guard', key: 'self' } as const, null as SessionRecord | null)
const others = atom({ plugin: 'collision-guard', key: 'others' } as const, [] as SessionRecord[])
const cleared = atom({ plugin: 'collision-guard', key: 'cleared' } as const, {} as Record<string, number>)

const EDIT_TOOLS = new Set(['Edit', 'Write', 'NotebookEdit'])

// Sessions already seen alive, so a newcomer gets a toast once; undefined until the first look.
let known: Set<string> | undefined
// Whether this module has read the other sessions' records yet (a reload starts over).
let hasLoaded = false

async function projectDir($: EngineInterface) {
  const home = (await $.env.get('HOME')) ?? '/tmp'
  return `${home}/.claude/collision-guard/${projectKey(await $.session.root())}`
}

// This session's record, started over under the new id after a /clear (its edits carried over, so the
// conversation does not collide with its own earlier changes).
async function ensureSelf($: EngineInterface): Promise<SessionRecord> {
  const [current, sessionId, root, now] = await Promise.all([read($, self), $.session.id(), $.session.root(), $.clock.now()])
  if (current && current.sessionId === sessionId) return current
  const fresh = { ...newRecord(sessionId, root, now), edits: current?.edits ?? [] }
  if (current) {
    await writeRecord($, { ...current, isEnded: true, isWorking: false, edits: [], updatedAt: now })
  }
  await update($, self, () => fresh)
  return fresh
}

async function writeRecord($: EngineInterface, record: SessionRecord) {
  await $.fs.write(`${await projectDir($)}/${record.sessionId}.json`, JSON.stringify(record))
}

async function changeSelf($: EngineInterface, change: (r: SessionRecord) => SessionRecord) {
  await ensureSelf($)
  const now = await $.clock.now()
  const next = await update($, self, r => (r ? { ...change(r), updatedAt: now } : r))
  if (next) await writeRecord($, next).catch(() => undefined)
}

// Every record in this project's folder but this session's; stale ones are removed on the way.
async function loadOthers($: EngineInterface): Promise<SessionRecord[]> {
  const dir = await projectDir($)
  const [entries, now, me] = await Promise.all([$.fs.list(dir).catch(() => []), $.clock.now(), $.session.id()])
  const records: SessionRecord[] = []
  for (const entry of entries) {
    if (!entry.name.endsWith('.json')) continue
    const record = parseRecord(await $.fs.read(`${dir}/${entry.name}`).catch(() => ''))
    if (!record || record.sessionId === me) continue
    if (isStale(record, now)) {
      await $.process.run(['rm', '-f', `${dir}/${entry.name}`]).catch(() => undefined)
      continue
    }
    records.push(record)
  }
  return records
}

async function refresh($: EngineInterface) {
  hasLoaded = true
  const all = await loadOthers($)
  await update($, others, () => all)
  const alive = liveOthers(all, await $.session.id(), await $.clock.now())
  const ids = new Set(alive.map(r => r.sessionId))
  if (known) {
    for (const r of alive) {
      if (!known.has(r.sessionId)) $.ui.toast(`Another Claude session is working in this folder: ${describe(r)}.`)
    }
  }
  known = ids
}

async function resolvePath($: EngineInterface, raw: string): Promise<string> {
  const stat = await $.fs.stat(raw, { resolve: true }).catch(() => undefined)
  return (stat as { realPath?: string } | undefined)?.realPath ?? raw
}

// Asks the person when another session changed the file recently; answers a deny reason, or undefined to go ahead.
async function checkCollision($: EngineInterface, path: string): Promise<string | undefined> {
  const all = await loadOthers($)
  const now = await $.clock.now()
  const hit = recentEditBy(all, await $.session.id(), path, now)
  if (!hit || !shouldAsk(hit, (await read($, cleared))[path])) return undefined
  const root = await $.session.root()
  const file = shortPath(path, root)
  const ago = formatAgo(now - hit.at)
  const state = workState(hit.record)
  const question = `Another session changed ${file} ${ago}: ${describe(hit.record)}, ${state}. Edit it here anyway?`
  const choice = await $.ui.ask(question, { options: [...CHOICES], header: 'Collision' }).catch(() => 'Cancel')
  if (choice === 'Proceed') {
    await update($, cleared, c => ({ ...c, [path]: hit.at }))
    return undefined
  }
  return denyReason(choice, describe(hit.record), file, ago)
}

async function setSteps($: EngineInterface, change: (steps: Step[]) => Step[]) {
  await changeSelf($, r => ({ ...r, steps: change(r.steps) }))
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const started = await next(e)
    await ensureSelf($)
    await changeSelf($, r => r)
    await refresh($).catch(() => undefined)
    let ticks = 0
    $.clock.every(5000, () => {
      ticks += 1
      void refresh($).catch(() => undefined)
      // The heartbeat: other sessions treat a record silent for 90 s as gone.
      if (ticks % 3 === 0) void changeSelf($, r => r)
    })
    return started
  })

  on('prompt.submit', async ($, e, next) => {
    if (e.command === undefined && !e.isMeta) {
      const task = firstLine(e.text)
      if (task) await changeSelf($, r => ({ ...r, task }))
    }
    return next(e)
  }).catch(($, e, next) => next(e))

  on('tool.call', async ($, e, next) => {
    const tool = String(e.tool)
    const args = e as unknown as Record<string, unknown>

    if (EDIT_TOOLS.has(tool)) {
      const raw = String(args.file_path ?? args.notebook_path ?? '')
      if (raw !== '') {
        const path = await resolvePath($, raw)
        const reason = await checkCollision($, path)
        if (reason !== undefined) return { deny: reason }
        const ran = await next(e)
        if (ran.deny === undefined && !ran.isError) {
          const now = await $.clock.now()
          await changeSelf($, r => ({ ...r, edits: recordEdit(r.edits, path, now) }))
        }
        return ran
      }
    }

    const ran = await next(e)
    if (ran.deny !== undefined || ran.isError || e.agentId !== undefined) return ran
    if (tool === 'mcp__ccd_turn__update_plan') {
      await setSteps($, s => applyUpdatePlan(s, args as Parameters<typeof applyUpdatePlan>[1]))
    } else if (tool === 'mcp__ccd_turn__wrap_up') {
      await setSteps($, s => s.map(x => ({ ...x, status: 'completed' })))
    } else if (tool === 'TodoWrite') {
      await setSteps($, () => applyTodoWrite((args.todos as Array<{ content: string; status: string }>) ?? []))
    } else if (tool === 'TaskCreate') {
      const task = (ran.result as { task?: { id?: string; subject?: string } } | undefined)?.task
      const id = task?.id
      if (id) await setSteps($, s => [...s.filter(x => x.id !== id), { id, content: task.subject ?? String(args.subject ?? ''), status: 'pending' }])
    } else if (tool === 'TaskUpdate') {
      await setSteps($, s => applyTaskUpdate(s, args as { taskId: string; status?: string; subject?: string }))
    }
    return ran
    // A failure in the check never blocks an edit: the call goes on as if the guard were not there.
  }).catch(($, e, next) => next(e))

  on('turn.start', async ($, e, next) => {
    if (e.agentId === undefined) await changeSelf($, r => ({ ...r, isWorking: true }))
    return next(e)
  })

  on('turn.complete', async ($, e, next) => {
    const result = await next(e)
    if (e.agentId === undefined) await changeSelf($, r => ({ ...r, isWorking: false }))
    return result
  })

  on('session.end', async ($, e, next) => {
    // Kept as ended, so its recent edits still warn other sessions for 30 minutes.
    await changeSelf($, r => ({ ...r, isWorking: false, isEnded: e.reason !== 'clear' }))
    return next(e)
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const below = await next(e)
    if (e.props.hasSurvey) return below
    const [stored, me, now, root] = await Promise.all([read($, others), $.session.id(), $.clock.now(), $.session.root()])
    // Before the first refresh (a fresh load), read the records directly; a draw may not write state.
    let all = stored
    if (!hasLoaded) {
      all = await loadOthers($).catch(() => [])
      $.clock.after(0, () => void refresh($).catch(() => undefined))
    }
    const alive = liveOthers(all, me, now)
    if (alive.length === 0) return below
    const { Box, Text } = $.ui.resolve(e)

    const banner = (
      <Box flexDirection="column">
        <Text color="warning" bold>
          {alive.length === 1 ? 'Another session is working in this folder' : `${alive.length} other sessions are working in this folder`}
        </Text>
        {alive.map(r => {
          const state = workState(r)
          const color = state === 'in progress' ? 'claude' : state === 'done' ? 'success' : 'warning'
          const step = currentStep(r)
          const files = [...r.edits].reverse().map(x => shortPath(x.path, root))
          const fileNote =
            files.length === 0
              ? 'no files changed in the last 30 min'
              : `changed ${files.slice(0, 3).join(', ')}${files.length > 3 ? ` and ${files.length - 3} more` : ''}`
          return (
            <Text key={r.sessionId} wrap="truncate-end">
              <Text color={color}>● {state}</Text>
              <Text> {r.task ?? 'no request yet'}</Text>
              <Text dimColor>
                {step ? ` · now: ${step}` : ''} · {fileNote} · {r.sessionId.slice(0, 8)}, seen {formatAgo(now - r.updatedAt)}
              </Text>
            </Text>
          )
        })}
      </Box>
    )
    return below ? (
      <Box flexDirection="column">
        {banner}
        {below}
      </Box>
    ) : (
      banner
    )
  })
}

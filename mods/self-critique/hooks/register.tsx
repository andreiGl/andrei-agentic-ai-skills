import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Reviewer, Review } from '../types'
import { FORK_PROMPT, REVIEWERS, fixPrompt, isReviewer, lastExchange, parseCritique, standalonePrompt } from './logic'

const PANE = 'self-critique'
const TITLE = 'Self-Critique'
const STORE_AUTO = 'isAuto'
const STORE_REVIEWER = 'reviewer'

const review = atom({ plugin: 'self-critique', key: 'review' } as const, { status: 'empty' } as Review)
const reviewer = atom({ plugin: 'self-critique', key: 'reviewer' } as const, 'session' as Reviewer)
const isAuto = atom({ plugin: 'self-critique', key: 'isAuto' } as const, false)

function reviewerLabel(value: Reviewer) {
  return REVIEWERS.find(r => r.value === value)?.label ?? value
}

function openPane($: EngineInterface) {
  return $.ui.open({ id: PANE, title: TITLE }).catch(() => undefined)
}

// Reviews the last response with the chosen reviewer and puts the result in the panel.
async function runReview($: EngineInterface) {
  if ((await read($, review)).status === 'running') return
  const who = await read($, reviewer)
  await update($, review, (): Review => ({ status: 'running', reviewer: who }))
  const fail = (message: string) => update($, review, (): Review => ({ status: 'error', reviewer: who, message }))
  try {
    let text: string
    if (who === 'session') {
      // The session's own model over its own transcript: it sees everything, and the prompt cache serves the history.
      const reply = await $.model.fork({ prompt: FORK_PROMPT })
      if (!reply.isAnswered) {
        await fail(reply.reason === 'nothing-to-fork' ? 'There is no response to review yet.' : `The review did not come back (${reply.reason}).`)
        return
      }
      text = reply.text
    } else {
      const exchange = lastExchange(await $.session.messages())
      if (!exchange) {
        await fail('There is no response to review yet.')
        return
      }
      const reply = await $.model.complete({ model: who, prompt: standalonePrompt(exchange), maxTokens: 4000 })
      if (!reply.isAnswered) {
        await fail(`The review did not come back (${reply.reason}).`)
        return
      }
      text = reply.text
    }
    const critique = parseCritique(text)
    if (!critique) {
      await fail('The reviewer answered, but not in the expected form. Press Rerun to try again.')
      return
    }
    const now = await $.clock.now()
    await update($, review, (): Review => ({ status: 'done', reviewer: who, critique, reviewedAt: now, sent: [] }))
  } catch (err) {
    await fail(`The review failed: ${err instanceof Error ? err.message : String(err)}`)
  }
}

async function makeFix($: EngineInterface, index: number) {
  const current = await read($, review)
  if (current.status !== 'done') return
  const flaw = current.critique.flaws[index]
  if (!flaw || current.sent.includes(index)) return
  // The person pressed the button, so the prompt goes in as their own words.
  await $.prompt.submit({ text: fixPrompt(flaw), asUser: true })
  await update($, review, r => (r.status === 'done' ? { ...r, sent: [...r.sent, index] } : r))
}

async function setAuto($: EngineInterface, value: boolean) {
  await update($, isAuto, () => value)
  await $.store.set(STORE_AUTO, value)
}

async function setReviewer($: EngineInterface, value: Reviewer) {
  await update($, reviewer, () => value)
  await $.store.set(STORE_REVIEWER, value)
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const started = await next(e)
    const savedAuto = await $.store.get(STORE_AUTO)
    const savedReviewer = await $.store.get(STORE_REVIEWER)
    await update($, isAuto, () => savedAuto === true)
    if (isReviewer(savedReviewer)) await update($, reviewer, () => savedReviewer)
    await $.command.register({
      name: 'critique',
      description: "Review Claude's last response in a side panel (auto on|off, model session|opus|sonnet|haiku)",
      argumentHint: '[auto on|auto off|model <name>]',
    })
    return started
  })

  on('command.run', { command: 'critique' }, async ($, e) => {
    const words = e.args.trim().toLowerCase().split(/\s+/).filter(Boolean)
    if (words[0] === 'auto') {
      const value = words[1] !== 'off'
      await setAuto($, value)
      await openPane($)
      return { text: `Self-Critique: auto review ${value ? 'on: every finished turn is reviewed' : 'off'}.` }
    }
    if (words[0] === 'model') {
      const name = words[1] === 'same' ? 'session' : words[1]
      if (!isReviewer(name)) return { text: 'Usage: /critique model session|opus|sonnet|haiku' }
      await setReviewer($, name)
      return { text: `Self-Critique: reviewer is now ${reviewerLabel(name)}.` }
    }
    await openPane($)
    void runReview($)
    return { text: `Self-Critique: reviewing the last response with ${reviewerLabel(await read($, reviewer))}…` }
  })

  on('turn.complete', async ($, e, next) => {
    const result = await next(e)
    if (e.agentId === undefined && !e.isAborted && (await read($, isAuto))) {
      $.clock.after(300, () => {
        void openPane($)
        void runReview($)
      })
    }
    return result
  })

  on('session.end', async ($, e, next) => {
    if (e.reason === 'clear') await update($, review, (): Review => ({ status: 'empty' }))
    return next(e)
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const table = $.ui.resolve(e)
    const { Box, Button, Text } = table
    const Select = 'Select' in table ? table.Select : undefined
    const [current, who, auto] = await Promise.all([read($, review), read($, reviewer), read($, isAuto)])
    const isRunning = current.status === 'running'

    const picker = Select ? (
      <Select
        key="reviewer"
        label="Reviewer"
        options={REVIEWERS}
        value={who}
        onSelect={value => (isReviewer(value) ? setReviewer($, value) : undefined)}
      />
    ) : (
      // A surface with no picker: one button steps through the reviewers.
      <Button
        key="reviewer"
        label={`Reviewer: ${reviewerLabel(who)}`}
        onPress={() => {
          const at = REVIEWERS.findIndex(r => r.value === who)
          return setReviewer($, REVIEWERS[(at + 1) % REVIEWERS.length]!.value)
        }}
      />
    )

    const controls = (
      <Box flexDirection="column">
        <Box flexDirection="row">
          <Button key="rerun" variant="primary" label={isRunning ? 'Reviewing…' : 'Rerun'} onPress={() => runReview($)} />
          <Text> </Text>
          <Button key="auto" label={`Auto: ${auto ? 'on' : 'off'}`} onPress={() => setAuto($, !auto)} />
        </Box>
        {picker}
      </Box>
    )

    if (current.status === 'empty') {
      return (
        <Box flexDirection="column">
          {controls}
          <Text> </Text>
          <Text dimColor>Press Rerun, or type /critique, to review Claude's last response.</Text>
        </Box>
      )
    }
    if (current.status === 'running') {
      return (
        <Box flexDirection="column">
          {controls}
          <Text> </Text>
          <Text dimColor>Reviewing the last response with {reviewerLabel(current.reviewer)}…</Text>
        </Box>
      )
    }
    if (current.status === 'error') {
      return (
        <Box flexDirection="column">
          {controls}
          <Text> </Text>
          <Text color="error" wrap="wrap">
            {current.message}
          </Text>
        </Box>
      )
    }

    const { critique } = current
    const color = { Strong: 'success', Mixed: 'warning', Weak: 'error' }[critique.verdict]
    return (
      <Box flexDirection="column">
        {controls}
        <Text> </Text>
        <Text>
          <Text bold color={color}>
            {critique.verdict}
          </Text>
          <Text dimColor> · reviewed by {reviewerLabel(current.reviewer)}</Text>
        </Text>
        {critique.summary !== '' && <Text wrap="wrap">{critique.summary}</Text>}
        <Text> </Text>
        <Text bold>Strengths</Text>
        {critique.strengths.length === 0 && <Text dimColor>None named.</Text>}
        {critique.strengths.map((s, n) => (
          <Text key={`strength-${n}`} wrap="wrap">
            <Text color="success">+ </Text>
            {s}
          </Text>
        ))}
        <Text> </Text>
        <Text bold>Flaws</Text>
        {critique.flaws.length === 0 && <Text dimColor>None found.</Text>}
        {critique.flaws.map((f, n) => {
          const isSent = current.sent.includes(n)
          return (
            <Box key={`flaw-${n}`} flexDirection="column">
              <Text wrap="wrap">
                <Text color="error">{n + 1}. </Text>
                {f.flaw}
              </Text>
              {f.fix !== '' && (
                <Text wrap="wrap" dimColor>
                  {'   '}Fix: {f.fix}
                </Text>
              )}
              <Box flexDirection="row">
                <Text>{'   '}</Text>
                {isSent ? (
                  <Text dimColor>Sent to Claude</Text>
                ) : (
                  <Button key={`fix-${n}`} label="Make this fix" onPress={() => makeFix($, n)} />
                )}
              </Box>
              <Text> </Text>
            </Box>
          )
        })}
      </Box>
    )
  })
}

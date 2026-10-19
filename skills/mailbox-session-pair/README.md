# mailbox-session-pair

Wire a new pair of named mailbox sessions (one per lane - e.g. TestWork on
work, TestHome on home) to a mailbox thread so they can exchange
session-addressed mail.

## Use the mod when it is installed

The `mailbox-band` Claude Code mod (`~/.claude/mods/mailbox-band/`) automates
this whole procedure: its **Wire...** button (shown on unmapped sessions)
prefills `/mailbox-wire <name> <predicted-thread>`, and the command verifies
the thread exists, writes the map line, and prints the peer-half
instruction. This skill is the documented manual procedure - use it when the
mod is not installed, or to understand what the mod does.

## What the skill does

Takes a session NAME on this lane and a thread number, wires them into
`~/.claude/mailbox/sessions` (`NAME:sessionid8:threads`), verifies the
mapping with the script's own prefix-match rule, and posts the peer half of
the setup to the thread as mailbox mail. See SKILL.md for the phased
procedure and the failure modes (stale prefixes after resume/compact/fork,
duplicate map lines, thread numbers that must exist first).

## Semantics worth knowing

- The thread number is the same on both lanes - one GitHub issue, both
  daemons read the same repo.
- Actor names are lane-qualified (`work/testwork`, `home/testhome`), so the
  two lanes may mirror the name or differ; it only must be unique within one
  machine's sessions map.
- The user starts the sessions; this skill (or the mod) wires a
  running session.

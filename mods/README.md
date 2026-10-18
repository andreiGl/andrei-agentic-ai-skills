# Mods

Function-hook plugins that change Claude Code's own interface: bands above the
prompt, side panels, dialogs on tool calls. Each folder is its own plugin, with a
README describing what it shows, its commands, and a fenced prompt that rebuilds
it from scratch in a fresh session.

| Mod | What it does | Rebuild prompt |
| :--- | :--- | :--- |
| [`session-keeper`](session-keeper/) | Prompt-cache countdown, usage limits and cost on one row; context fill with a quality warning and one-key handoff on the other. | [README](session-keeper/README.md) |
| [`plan-progress`](plan-progress/) | Side panel with the goal, phase, checklist, progress bar and elapsed time of the current plan; All tasks tab across sessions; chime when a turn ends. | [README](plan-progress/README.md) |
| [`self-critique`](self-critique/) | `/critique` reviews Claude's last response in a side panel: verdict, strengths, flaws with one-click fixes. | [README](self-critique/README.md) |
| [`collision-guard`](collision-guard/) | Asks before editing a file another session changed in the last 30 minutes; banner listing the other sessions in the folder. | [README](collision-guard/README.md) |

## Installing

Two routes. The repository's root marketplace lists every mod, so on any machine:

```
claude plugin marketplace add andreiGl/andrei-agentic-ai-skills
claude plugin install session-keeper@andrei-personal-skills
```

Or, from a clone of this repository, install a folder marketplace that lists the
same four (see `.claude-plugin/marketplace.json` here):

```
claude plugin marketplace add <clone>/mods
claude plugin install session-keeper@local-mods
```

In the desktop app, run the install from a terminal: desktop sessions load
plugins installed at the user scope, whichever route installed them.

## Notes

- The mod API is early access and moves between Claude Code releases; the mods
  were last verified on 2.1.302. Each mod's rebuild prompt says to check every
  call against the running build's API types first.
- Run a mod's tests from its own folder (`claude plugin test mods/<name>`). A run
  from the repository root also collects these tests, and the drawing tests fail
  there because they run against the root plugin instead of their own.
- Engine-laid files: when a desktop session loads a mod from its folder, Claude
  Code writes `.claude-plugin/types/` and `tsconfig.json` beside the source. They
  are self-ignored inside the dev workspace and ignored at the repo level; do not
  commit them.
- Uninstalling a plugin deletes its `$.store` data (the mods' saved settings).

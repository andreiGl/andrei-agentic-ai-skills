#!/usr/bin/env python3
"""SessionStart check for knowledge-base maintenance triggers.

Evaluates the "Run when any of these holds" conditions of synthesize-knowledge
and check-knowledge against the knowledge base and prints one context line when
either is due. Plain stdout from a SessionStart hook is injected into model
context; silence when nothing is due. KB_ROOT overrides the knowledge base for
testing.
"""
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

KB = Path(os.environ.get("KB_ROOT", Path.home() / ".claude" / "knowledge"))

SYNTH_EXPERIENCE_THRESHOLD = 5
SYNTH_LEARNINGS_THRESHOLD = 20
CHECK_MAX_AGE_DAYS = 14      # two weeks


def last_verified():
    """Read Last verified from the INDEX.md KB status block."""
    try:
        text = (KB / "INDEX.md").read_text()
    except OSError:
        return None
    verified = None
    for line in text.splitlines():
        match = re.match(r"\*\*Last verified:\*\* (\S+)", line)
        if match:
            verified = match.group(1)
    return verified


def days_since(value):
    try:
        return (date.today() - date.fromisoformat(value)).days
    except (TypeError, ValueError):
        return None


def main():
    # Consume the hook stdin JSON so the pipe never blocks.
    try:
        json.load(sys.stdin)
    except Exception:
        pass

    experiences = KB / "experiences"
    if not experiences.is_dir():
        return
    exp_count = len(list(experiences.glob("*.md")))
    try:
        learn_count = sum(
            1 for line in (KB / "learnings.md").read_text().splitlines()
            if line.startswith("## ")
        )
    except OSError:
        learn_count = 0

    # An empty knowledge base (fresh install with template dates) has nothing
    # to maintain: stay silent until the first entry lands.
    if exp_count == 0 and learn_count == 0:
        return

    verified = last_verified()
    check_age = days_since(verified)

    synth_reasons = []
    if exp_count >= SYNTH_EXPERIENCE_THRESHOLD:
        synth_reasons.append(
            f"experiences/ holds {exp_count} entries (threshold {SYNTH_EXPERIENCE_THRESHOLD})"
        )
    if learn_count > SYNTH_LEARNINGS_THRESHOLD:
        synth_reasons.append(
            f"learnings.md holds {learn_count} entries (threshold {SYNTH_LEARNINGS_THRESHOLD})"
        )

    if synth_reasons:
        print(
            "Knowledge base maintenance due - synthesize-knowledge: "
            + "; ".join(synth_reasons)
            + ". Run the synthesize-knowledge skill before starting other work."
        )
        return

    if check_age is None or check_age > CHECK_MAX_AGE_DAYS:
        when = "never" if not verified else f"{verified} ({check_age} days ago)"
        print(
            f"Knowledge base maintenance due - check-knowledge: last verified {when}. "
            "Run the check-knowledge skill before starting a large task."
        )


if __name__ == "__main__":
    main()

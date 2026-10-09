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

KB = Path(os.environ.get("KB_ROOT") or Path.home() / ".claude" / "knowledge")

SYNTH_EXPERIENCE_THRESHOLD = 5
SYNTH_LEARNINGS_THRESHOLD = 20
SYNTH_MAX_AGE_DAYS = 61      # ~2 months
CHECK_MAX_AGE_DAYS = 14      # two weeks


def status_dates():
    """Read Last verified / Last synthesized from the INDEX.md KB status block.

    Either layout: INDEX.md under knowledge/ or at the KB root.
    """
    index = KB / "knowledge" / "INDEX.md"
    if not index.exists():
        index = KB / "INDEX.md"
    try:
        text = index.read_text()
    except OSError:
        return None, None
    verified = synthesized = None
    for line in text.splitlines():
        # First match wins - a duplicated stamp line must not change the
        # reading. Only a plain YYYY-MM-DD stamp counts; a datetime stamp is a
        # typo to flag, not a value to parse a prefix from. The literal
        # template stamp "never" is reported as-is (this install nags on it -
        # the work install exempts it), everything else reads as missing.
        if verified is None:
            if re.match(r"\*\*Last verified:\*\* never$", line):
                verified = "never"
            else:
                match = re.match(r"\*\*Last verified:\*\* (\d{4}-\d{2}-\d{2})$", line)
                if match:
                    verified = match.group(1)
        if synthesized is None:
            if re.match(r"\*\*Last synthesized:\*\* never$", line):
                synthesized = "never"
            else:
                match = re.match(r"\*\*Last synthesized:\*\* (\d{4}-\d{2}-\d{2})$", line)
                if match:
                    synthesized = match.group(1)
    return verified, synthesized


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

    verified, synthesized = status_dates()
    synth_age = days_since(synthesized)
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
    if synth_age is None:
        synth_reasons.append(
            f"INDEX.md Last synthesized is {synthesized or 'missing'}"
        )
    elif synth_age < 0:
        # A future-dated stamp is a typo; left alone it would silence both
        # checks for years.
        synth_reasons.append(f"Last synthesized {synthesized} is in the future")
    elif synth_age > SYNTH_MAX_AGE_DAYS:
        synth_reasons.append(f"last synthesized {synthesized} ({synth_age} days ago)")

    if synth_reasons:
        print(
            "Knowledge base maintenance due - synthesize-knowledge: "
            + "; ".join(synth_reasons)
            + ". Run the synthesize-knowledge skill before starting other work."
        )
        return

    if check_age is None or check_age < 0 or check_age > CHECK_MAX_AGE_DAYS:
        if not verified:
            # Absent line, literal "never" stamp, or a malformed value (a
            # datetime typo): the stamp names which, when it has a value.
            when = verified or "never"
        elif check_age is not None and check_age < 0:
            when = f"{verified} (in the future - typo?)"
        elif check_age is None:
            # Shape-valid but calendar-impossible ("2026-13-45"): not None.
            when = f"{verified} (not a real date - typo?)"
        else:
            when = f"{verified} ({check_age} days ago)"
        print(
            f"Knowledge base maintenance due - check-knowledge: last verified {when}. "
            "Run the check-knowledge skill before starting a large task."
        )


if __name__ == "__main__":
    main()

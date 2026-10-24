#!/usr/bin/env python3
"""activation-run.py - build, run, and score a skill activation suite.

Design adapted from UiPath/coder-eval's check-skill skill (Apache-2.0), reduced to
what runs without the coder-eval CLI: each row is one headless `claude -p` session
in a sandbox that stages ONLY the skill under test; the criterion is the presence of
a Skill tool_use call naming that skill in the session's stream-json transcript.

Usage:
  activation-run.py <skill-dir> <rows.jsonl> [--run] [--keep-transcripts DIR]

  <skill-dir>   directory containing the target SKILL.md (name read from frontmatter)
  <rows.jsonl>  one JSON object per line: {"id", "expected_skill", "prompt"};
                expected_skill "" marks a distractor row
  --run         actually spawn sessions (default: dry plan - print what would run)
  --keep-transcripts DIR  copy raw transcripts here instead of deleting them

Scoring (same definitions as coder-eval):
  recall    = of the rows that should engage the skill, the fraction that did
  precision = of the rows where the skill engaged, the fraction that should have
Prints per-row verdicts, then recall / precision / F1 and a confusion matrix.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RUNNER = Path(__file__).with_name("activation-run.sh")
TIMEOUT_S = 300


def skill_name_from(skill_dir: Path) -> str:
    """Read the bare skill name from the frontmatter of skill_dir/SKILL.md."""
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    match = re.search(r"^name:\s*(\S+)\s*$", text, re.MULTILINE)
    if not match:
        sys.exit(f"activation-run: no 'name:' in {skill_dir}/SKILL.md frontmatter")
    return match.group(1)


def load_rows(rows_path: Path):
    rows = []
    for lineno, line in enumerate(rows_path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        for field in ("id", "expected_skill", "prompt"):
            if field not in row:
                sys.exit(f"activation-run: row {lineno} missing '{field}'")
        rows.append(row)
    return rows


def stage_plugin_root(skill_dir: Path, staging: Path) -> None:
    """Copy ONLY the skill under test into staging/skills/<name>/."""
    name = skill_name_from(skill_dir)
    dest = staging / "skills" / name
    shutil.copytree(skill_dir, dest)
    # A plugin root loads everything beside skills/ - nothing else is copied, so
    # the sandboxed agent sees exactly one skill and no hooks, agents, or commands.


def run_row(row: dict, staging: Path, keep_dir: Path | None) -> tuple[bool, str, float]:
    """Run one row; return (triggered, invoked_name, cost_usd)."""
    with tempfile.TemporaryDirectory(prefix="act-row-") as tmp:
        prompt_file = Path(tmp) / "prompt.txt"
        prompt_file.write_text(row["prompt"], encoding="utf-8")
        transcript = Path(tmp) / "stream.jsonl"
        proc = subprocess.run(
            ["bash", str(RUNNER), str(staging), str(prompt_file), str(transcript)],
            capture_output=True, text=True, timeout=TIMEOUT_S + 60,
        )
        if proc.returncode != 0 and not transcript.exists():
            return False, "", 0.0
        if keep_dir:
            shutil.copy(transcript, keep_dir / f"{row['id']}.jsonl")
        triggered, name, cost = False, "", 0.0
        for line in transcript.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "assistant":
                for block in event.get("message", {}).get("content", []):
                    if isinstance(block, dict) and block.get("type") == "tool_use" \
                            and block.get("name") == "Skill":
                        skill = str(block.get("input", {}).get("skill", ""))
                        # plugin-dir skills are namespaced <dirname>:<name>
                        skill = skill.split(":")[-1]
                        if skill:
                            name = skill
                            if skill == row["expected_skill"] or not row["expected_skill"]:
                                triggered = True
            if event.get("type") == "result":
                cost = float(event.get("total_cost_usd") or 0.0)
        return triggered, name, cost


def score(rows: list[dict], results: list[dict]) -> None:
    tp = sum(1 for r in results if r["expected"] and r["triggered"])
    fn = sum(1 for r in results if r["expected"] and not r["triggered"])
    fp = sum(1 for r in results if not r["expected"] and r["triggered"])
    tn = sum(1 for r in results if not r["expected"] and not r["triggered"])
    positives, negatives = tp + fn, fp + tn
    recall = tp / positives if positives else float("nan")
    precision = tp / (tp + fp) if (tp + fp) else float("nan")
    f1 = (2 * precision * recall / (precision + recall)
          if positives and negatives and (precision + recall) else float("nan"))
    print("\n=== Results ===")
    for r in results:
        mark = "HIT " if r["triggered"] else "miss"
        via = f" via {r['invoked']}" if r["invoked"] and r["invoked"] != r.get("expected_or_blank") else ""
        print(f"  [{mark}] {r['id']:<12} {'pos' if r['expected'] else 'neg'}{via}  ${r['cost']:.3f}")
    print(f"\nrecall={recall:.2f} ({tp}/{positives} positives)  "
          f"precision={precision:.2f} ({fp} false fires)  F1={f1:.2f}")
    print(f"confusion: TP={tp} FN={fn} FP={fp} TN={tn}")
    if positives and recall < 0.7:
        print("NOTE: low recall - rule out listing eviction before blaming wording;")
        print("      run the diagnose mode on the real environment first.")


def main() -> None:
    args = sys.argv[1:]
    do_run = "--run" in args
    keep_dir = None
    if "--keep-transcripts" in args:
        keep_dir = Path(args[args.index("--keep-transcripts") + 1])
        keep_dir.mkdir(parents=True, exist_ok=True)
    positional = [a for a in args if not a.startswith("--") and a != (str(keep_dir) if keep_dir else None)]
    if len(positional) != 2:
        sys.exit(__doc__)
    skill_dir, rows_path = Path(positional[0]), Path(positional[1])
    name = skill_name_from(skill_dir)
    rows = load_rows(rows_path)

    desc = ""
    front = re.search(r"^description:\s*(.+?)$", (skill_dir / "SKILL.md").read_text(encoding="utf-8"), re.MULTILINE)
    if front:
        desc = front.group(1).strip()
    if len(desc) > 1536:
        print(f"WARNING: description is {len(desc)} chars - past the 1536-char listing "
              f"cap; trigger text past it cannot affect activation. Shorten it.")

    print(f"skill: {name}   rows: {len(rows)} "
          f"({sum(1 for r in rows if r['expected_skill'])} pos / "
          f"{sum(1 for r in rows if not r['expected_skill'])} neg)")
    if not do_run:
        print("\nDRY PLAN (no sessions spawned). Rows to run:")
        for r in rows:
            kind = "pos" if r["expected_skill"] else "neg"
            print(f"  [{kind}] {r['id']}: {r['prompt'][:90]}")
        print("\nEach row is one full headless session (~$0.03-0.07 at flash tier).")
        print("Re-run with --run to execute. Add --keep-transcripts DIR to keep raw output.")
        return

    collisions = [r["id"] for r in rows if r["expected_skill"] and r["expected_skill"] != name]
    if collisions:
        sys.exit(f"activation-run: expected_skill must be '{name}' (or blank); "
                 f"mismatched rows: {collisions}")

    staging_root = Path(tempfile.mkdtemp(prefix="act-stage-"))
    stage_plugin_root(skill_dir, staging_root)
    try:
        results = []
        for i, row in enumerate(rows, 1):
            print(f"row {i}/{len(rows)}: {row['id']} ...", flush=True)
            triggered, invoked, cost = run_row(row, staging_root, keep_dir)
            results.append({
                "id": row["id"], "expected": bool(row["expected_skill"]),
                "expected_or_blank": row["expected_skill"],
                "triggered": triggered, "invoked": invoked, "cost": cost,
            })
        score(rows, results)
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""activation-run.py - build, run, and score a skill activation suite.

Design adapted from UiPath/coder-eval's check-skill skill (Apache-2.0), reduced to
what runs without the coder-eval CLI: each row is one headless `claude -p` session
in a sandbox that stages ONLY the labelled skills (the target plus any sibling a
routing row names); the criterion is the Skill tool_use calls in the session's
stream-json transcript.

Usage:
  activation-run.py <skill-dir> <rows.jsonl> [--run] [--keep-transcripts DIR]
                    [--allow-collision] [--repeat N]

  <skill-dir>   directory containing the target SKILL.md (name read from frontmatter)
  <rows.jsonl>  one JSON object per line: {"id", "expected_skill", "prompt"};
                expected_skill "" marks a distractor row; a sibling skill's name
                marks a routing row (the request belongs to that sibling)
  --run         actually spawn sessions (default: dry plan - print what would run)
  --keep-transcripts DIR  copy raw transcripts here instead of deleting them
  --allow-collision     proceed despite an installed-name collision (rarely right)
  --repeat N    N sessions per row (default 1); a row passes only if it passed in
                EVERY run - one flake shows as flaky. Per-row fire rates are
                printed when N > 1. Cost is N x the row count per measurement.

Row semantics:
  expected = target   -> PASS iff the target fired
  expected = sibling  -> PASS iff the sibling fired; firing the target is a misroute
  expected = ""       -> PASS iff nothing fired (distractor)

Scoring (target-centric, coder-eval definitions):
  recall    = of the rows that expect the target, the fraction where it fired
  precision = of the rows where the target fired, the fraction that expected it
Suite gate: recall >= 0.7 and precision >= 0.7 (printed as PASS/FAIL).
"""

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RUNNER = Path(__file__).with_name("activation-run.sh")
TIMEOUT_S = 300
RECALL_GATE = 0.7
PRECISION_GATE = 0.7


def skill_name_from(skill_dir: Path) -> str:
    """Read the bare skill name from the frontmatter of skill_dir/SKILL.md."""
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    match = re.search(r"^name:\s*(\S+)\s*$", text, re.MULTILINE)
    if not match:
        sys.exit(f"activation-run: no 'name:' in {skill_dir}/SKILL.md frontmatter")
    return match.group(1)


def description_from(skill_dir: Path) -> str:
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    match = re.search(r"^description:\s*(.+?)$", text, re.MULTILINE)
    return match.group(1).strip() if match else ""


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


def resolve_sibling(name: str, target_dir: Path) -> Path:
    """Find a sibling skill dir: next to the target, then user, then project skills."""
    for base in (target_dir.parent, Path.home() / ".claude" / "skills",
                 Path.cwd() / ".claude" / "skills"):
        candidate = base / name
        if (candidate / "SKILL.md").is_file():
            return candidate
    sys.exit(f"activation-run: sibling skill '{name}' not found next to the target, "
             f"in ~/.claude/skills, or in ./.claude/skills - cannot stage it")


def scan_installed_collisions(wanted: list) -> list:
    """Scan user and project skill dirs for bare-name collisions with the suite's
    skills. A collision means the real environment may activate the wrong skill, so
    a sandbox result would not transfer."""
    seen = {}
    for base in (Path.home() / ".claude" / "skills", Path.cwd() / ".claude" / "skills"):
        if not base.is_dir():
            continue
        for child in sorted(base.iterdir()):
            skill_md = child / "SKILL.md"
            if not skill_md.is_file():
                continue
            match = re.search(r"^name:\s*(\S+)\s*$", skill_md.read_text(encoding="utf-8"),
                              re.MULTILINE)
            if match:
                seen.setdefault(match.group(1), []).append(str(child))
    warnings = []
    for name in wanted:
        paths = seen.get(name, [])
        if len(paths) > 1:
            warnings.append(f"'{name}' installed at {len(paths)} locations: "
                            f"{', '.join(paths)}")
    return warnings


def stage_plugin_root(skill_dirs: list, staging: Path) -> None:
    """Copy ONLY the labelled skills into staging/skills/<name>/."""
    for skill_dir in skill_dirs:
        name = skill_name_from(skill_dir)
        dest = staging / "skills" / name
        shutil.copytree(skill_dir, dest)
    # A plugin root loads everything beside skills/ - nothing else is copied, so
    # the sandboxed agent sees exactly the staged skills and no hooks, agents, or
    # commands.


def run_row(row: dict, staging: Path, keep_dir: Path | None, repeat: int) -> tuple:
    """Run one row `repeat` times; return (per_run_invoked_lists, per_run_costs).

    Each element of per_run_invoked_lists is the skill names one session invoked.
    Callers aggregate: a strict pass is every run carrying the expected verdict.
    """
    per_run_invoked, per_run_costs = [], []
    for run_index in range(repeat):
        with tempfile.TemporaryDirectory(prefix="act-row-") as tmp:
            prompt_file = Path(tmp) / "prompt.txt"
            prompt_file.write_text(row["prompt"], encoding="utf-8")
            transcript = Path(tmp) / "stream.jsonl"
            try:
                proc = subprocess.run(
                    ["bash", str(RUNNER), str(staging), str(prompt_file),
                     str(transcript)],
                    capture_output=True, text=True, timeout=TIMEOUT_S + 60,
                )
            except subprocess.TimeoutExpired:
                per_run_invoked.append([])
                per_run_costs.append(0.0)
                continue
            if proc.returncode != 0 and not transcript.exists():
                per_run_invoked.append([])
                per_run_costs.append(0.0)
                continue
            if keep_dir:
                suffix = f".run{run_index + 1}" if repeat > 1 else ""
                shutil.copy(transcript, keep_dir / f"{row['id']}{suffix}.jsonl")
            invoked, cost = [], 0.0
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
                            if skill and skill not in invoked:
                                invoked.append(skill)
                if event.get("type") == "result":
                    cost = float(event.get("total_cost_usd") or 0.0)
            per_run_invoked.append(invoked)
            per_run_costs.append(cost)
    return per_run_invoked, per_run_costs


def row_kind(row: dict, target: str) -> str:
    if not row["expected_skill"]:
        return "neg"
    return "pos" if row["expected_skill"] == target else "sib"


def score(rows: list, results: list, target: str, repeat: int = 1) -> None:
    """Score per-run results. A row's verdict is strict: it passes only if EVERY
    run passed its own check. With repeat > 1, per-row fire rates are printed.

    Per-run check (same row semantics as single-run mode):
      expected = target   -> the target fired
      expected = sibling  -> the sibling fired
      expected = ""       -> nothing fired
    """
    def run_passed(r: dict, invoked: list) -> bool:
        expected = r["expected"]
        if not expected:
            return not invoked
        return expected in invoked

    tp = sum(1 for r in results if r["expected"] == target
             and all(target in inv for inv in r["runs"]))
    fn = len([r for r in results if r["expected"] == target
              and not all(target in inv for inv in r["runs"])])
    fp = sum(1 for r in results if r["expected"] != target
             and any(target in inv for inv in r["runs"]))
    negatives = [r for r in results if r["expected"] == ""]
    siblings = [r for r in results if r["expected"] not in ("", target)]
    positives = tp + fn
    target_fires = tp + fp
    recall = tp / positives if positives else float("nan")
    precision = tp / target_fires if target_fires else float("nan")
    f1 = (2 * precision * recall / (precision + recall)
          if positives and target_fires and (precision + recall) else float("nan"))

    print(f"\n=== Results ({repeat} run{'s' if repeat > 1 else ''} per row; "
          f"row passes only if every run passed) ===")
    for r in results:
        per_run = [run_passed(r, inv) for inv in r["runs"]]
        ok = all(per_run)
        mark = "PASS" if ok else "MISS"
        kind = row_kind({"expected_skill": r["expected"]}, target)
        via = f" via {r['runs'][0][0]}" if r["runs"] and r["runs"][0] else ""
        rate = ""
        if repeat > 1 and not ok:
            fired = sum(1 for inv in r["runs"]
                        if (r["expected"] in inv if r["expected"] else not inv))
            rate = f"  fired {fired}/{repeat}"
        print(f"  [{mark}] {r['id']:<12} {kind:<4}{via}  "
              f"${sum(r['costs']):.3f}{rate}")

    tn = sum(1 for r in negatives if not any(r["runs"]))
    fp_neg = len(negatives) - tn
    routed = sum(1 for r in siblings if all(r["expected"] in inv for inv in r["runs"]))
    misrouted = sum(1 for r in siblings
                    if any(target in inv for inv in r["runs"])
                    and not all(r["expected"] in inv for inv in r["runs"]))
    sib_missed = len(siblings) - routed - misrouted
    print(f"\nrecall={recall:.2f} ({tp}/{positives} target rows)  "
          f"precision={precision:.2f} ({fp} false target fires)  F1={f1:.2f}")
    print(f"confusion: TP={tp} FN={fn} FP={fp} (distractor fires {fp_neg}) TN={tn}")
    if siblings:
        print(f"sibling routing: {routed} correct, {misrouted} misrouted to target, "
              f"{sib_missed} missed")

    checks = []
    gate = True
    if positives:
        checks.append(f"recall {recall:.2f} {'>=' if recall >= RECALL_GATE else '<'} "
                      f"{RECALL_GATE:.2f}")
        gate = gate and recall >= RECALL_GATE
    if target_fires:
        checks.append(f"precision {precision:.2f} "
                      f"{'>=' if precision >= PRECISION_GATE else '<'} "
                      f"{PRECISION_GATE:.2f}")
        gate = gate and precision >= PRECISION_GATE
    if checks:
        print(f"suite gate ({RECALL_GATE:.2f}/{PRECISION_GATE:.2f}): "
              f"{'PASS' if gate else 'FAIL'} - {', '.join(checks)}")
    if positives and recall < RECALL_GATE:
        print("NOTE: low recall - rule out listing eviction before blaming wording;")
        print("      run the diagnose mode on the real environment first.")
    if misrouted:
        print("NOTE: misroutes concentrated on a sibling = boundary dispute between")
        print("      two descriptions; state what EACH skill is not for, fix both.")


def main() -> None:
    args = sys.argv[1:]
    do_run = "--run" in args
    allow_collision = "--allow-collision" in args
    keep_dir = None
    if "--keep-transcripts" in args:
        idx = args.index("--keep-transcripts")
        keep_dir = Path(args[idx + 1])
        keep_dir.mkdir(parents=True, exist_ok=True)
        del args[idx:idx + 2]
    repeat = 1
    if "--repeat" in args:
        idx = args.index("--repeat")
        repeat = int(args[idx + 1])
        if repeat < 1:
            sys.exit("activation-run: --repeat must be >= 1")
        del args[idx:idx + 2]
    positional = [a for a in args if not a.startswith("--")]
    if len(positional) != 2:
        sys.exit(__doc__)
    skill_dir, rows_path = Path(positional[0]), Path(positional[1])
    name = skill_name_from(skill_dir)
    rows = load_rows(rows_path)

    desc = description_from(skill_dir)
    if len(desc) > 1536:
        print(f"WARNING: description is {len(desc)} chars - past the 1536-char listing "
              f"cap; trigger text past it cannot affect activation. Shorten it.")

    # Validate row labels and resolve every sibling to a stageable directory.
    expected_names = sorted({r["expected_skill"] for r in rows if r["expected_skill"]})
    bad = [n for n in expected_names if n != name and not n.isidentifier()]
    sibling_names = [n for n in expected_names if n != name]
    sibling_dirs = {n: resolve_sibling(n, skill_dir) for n in sibling_names}

    collisions = scan_installed_collisions([name] + sibling_names)
    if collisions:
        for warning in collisions:
            print(f"COLLISION: {warning}")
        if not allow_collision:
            sys.exit("activation-run: an installed-name collision means the suite may "
                     "measure the wrong skill; resolve it, or pass --allow-collision "
                     "to proceed anyway")

    n_pos = sum(1 for r in rows if r["expected_skill"] == name)
    n_neg = sum(1 for r in rows if not r["expected_skill"])
    n_sib = len(rows) - n_pos - n_neg
    print(f"skill: {name}   rows: {len(rows)} ({n_pos} pos / {n_neg} neg / {n_sib} sib)")
    if sibling_dirs:
        for sib, path in sibling_dirs.items():
            print(f"  stages sibling '{sib}' from {path}")

    if not do_run:
        print(f"\nDRY PLAN (no sessions spawned). Rows to run"
              f"{f' x {repeat}' if repeat > 1 else ''}:")
        for r in rows:
            kind = row_kind(r, name)
            print(f"  [{kind}] {r['id']}: {r['prompt'][:90]}")
        print(f"\nEach row is one full headless session per run "
              f"(~$0.03-0.07 at flash tier); {len(rows) * repeat} sessions total.")
        print("Re-run with --run to execute. Add --keep-transcripts DIR to keep raw output.")
        return

    staging_root = Path(tempfile.mkdtemp(prefix="act-stage-"))
    stage_plugin_root([skill_dir] + list(sibling_dirs.values()), staging_root)
    try:
        results = []
        for i, row in enumerate(rows, 1):
            runs_label = f" (x{repeat})" if repeat > 1 else ""
            print(f"row {i}/{len(rows)}: {row['id']}{runs_label} ...", flush=True)
            runs, costs = run_row(row, staging_root, keep_dir, repeat)
            results.append({"id": row["id"], "expected": row["expected_skill"],
                            "runs": runs, "costs": costs})
        score(rows, results, name, repeat)
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)


if __name__ == "__main__":
    main()

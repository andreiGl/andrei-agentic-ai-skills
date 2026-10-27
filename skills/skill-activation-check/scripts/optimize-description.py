#!/usr/bin/env python3
"""optimize-description.py - close the measure-edit-measure loop on a skill description.

Mechanism adapted from anthropics/skills skill-creator's Description Optimization
(Apache-2.0/MIT-licensed repo), re-based on our sandboxed activation runner: the loop
proposes description rewrites from measured failures, re-measures each candidate with
real headless sessions, and selects by held-out test score so the description fits
queries it was not tuned on.

Usage:
  optimize-description.py <skill-dir> <eval-set.jsonl> [--iterations N] [--runs-per-query N]

  <skill-dir>     directory containing the target SKILL.md (edited in place; git
                  recommended - the loop rewrites the description repeatedly)
  <eval-set.jsonl> one {"id", "expected_skill", "prompt"} object per line - the
                  same row format activation-run.py takes; write it with activation-
                  check's row discipline: positives paraphrase, negatives are NEAR MISSES
                  that share vocabulary with the description, not obviously irrelevant
  --iterations    rewrite rounds (default 3)
  --runs-per-query  sessions per query per measurement (default 1; 3 gives a stabler
                  trigger rate at N-times the cost)

Cost model: one full headless session per (query x runs-per-query) per measured
description. A 20-query set at 1 run/query costs 20 sessions per candidate measured.
The script prints the running total and asks nothing - confirm the budget yourself
before starting.

Safety: measurement reuses activation-run.py's sandbox unchanged (temp HOME +
CLAUDE_CONFIG_DIR, minimal plugin root, tools locked to Skill + read-only). Only the
description inside the staged SKILL.md changes between measurements; the body is
never touched. The proposal step runs `claude -p` with the skill body and failure
data on stdin - its output is parsed as a JSON description string, never executed.
"""

import json
import random
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
RUNNER_SCRIPT = HERE / "activation-run.py"
RUNS_PER_QUERY_DEFAULT = 1
PROPOSAL_TIMEOUT_S = 300
DESCRIPTION_CAP = 1536


def read_description(skill_dir: Path) -> str:
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    match = re.search(r"^description:\s*(.+?)$", text, re.MULTILINE)
    if not match:
        sys.exit(f"optimize-description: no description in {skill_dir}/SKILL.md")
    return match.group(1).strip()


def write_description(skill_dir: Path, description: str) -> None:
    """Replace only the description line in SKILL.md frontmatter.

    Writing the already-present description is a no-op, not an error - the loop
    restores the best-known description after every measurement, and that is
    frequently the text currently in the file.
    """
    path = skill_dir / "SKILL.md"
    text = path.read_text(encoding="utf-8")
    if not re.search(r"(?m)^description:", text):
        sys.exit("optimize-description: no description line in SKILL.md")
    new = re.sub(r"(?m)^description:\s*.+?$", f"description: {description}", text, count=1)
    if new != text:
        path.write_text(new, encoding="utf-8")


def split_eval_set(rows: list, holdout: float = 0.4, seed: int = 42):
    """Stratified split: positives and negatives divided separately (adapted from
    run_loop.py's split_eval_set)."""
    positives = [r for r in rows if r["expected_skill"]]
    negatives = [r for r in rows if not r["expected_skill"]]
    rng = random.Random(seed)
    rng.shuffle(positives)
    rng.shuffle(negatives)
    n_pos = max(1, int(len(positives) * holdout)) if positives else 0
    n_neg = max(1, int(len(negatives) * holdout)) if negatives else 0
    test = positives[:n_pos] + negatives[:n_neg]
    train = positives[n_pos:] + negatives[n_neg:]
    return train, test


def measure(rows: list, skill_dir: Path, runs_per_query: int) -> dict:
    """Run the activation suite on rows; return {query_id: passed_bool} and cost."""
    # Build a fresh temp staging of the skill (with its CURRENT description) so each
    # measurement reflects the candidate under test. activation-run.py re-stages
    # internally; we pass the skill dir through and aggregate its output.
    results: dict = {}
    total_cost = 0.0
    # activation-run.py scores a whole suite; run it once per measurement batch by
    # feeding it a temp rows file and parsing its per-row output.
    with tempfile.TemporaryDirectory(prefix="opt-measure-") as tmp:
        rows_file = Path(tmp) / "rows.jsonl"
        rows_file.write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        for _ in range(runs_per_query):
            proc = subprocess.run(
                [sys.executable, "-I", str(RUNNER_SCRIPT), str(skill_dir), str(rows_file),
                 "--run"],
                capture_output=True, text=True, timeout=600 * len(rows),
            )
            if proc.returncode != 0:
                # The runner exits 1 on any measurement failure (no gateway token,
                # setup error, errored session). Continuing would score the batch as
                # all-miss and feed fake failures to the proposal step - stop instead.
                stderr = (proc.stderr or "").strip()
                raise RuntimeError(
                    f"activation runner failed (exit {proc.returncode}): "
                    f"{stderr.splitlines()[-1] if stderr else '(no stderr)'}"
                    f" - measurement failure, not a miss; fix the login/harness and re-run")
            # Parse the per-row verdict lines: "  [PASS] <id> ..." / "  [MISS] <id> ..."
            for line in proc.stdout.splitlines():
                match = re.match(r"\s+\[(PASS|MISS)\]\s+(\S+)", line)
                if not match:
                    continue
                verdict, row_id = match.group(1), match.group(2)
                results.setdefault(row_id, []).append(verdict == "PASS")
            missing = [r["id"] for r in rows if r["id"] not in results]
            if missing:
                raise RuntimeError(
                    f"activation runner printed no verdict for rows {missing} "
                    f"- measurement failure, not a miss; fix the harness and re-run")
            # Per-row costs printed as "...  $0.123"; sum them all
            total_cost += sum(
                float(m) for m in re.findall(r"\$([0-9.]+)", proc.stdout))
    # A query passes iff it passed in every run (strict: one flake = flaky trigger)
    passed = {rid: all(v) for rid, v in results.items()}
    return {"passed": passed, "cost": total_cost,
            "measured": {rid: len(v) for rid, v in results.items()}}


def score(rows: list, passed: dict, name: str) -> tuple:
    """Return (recall, precision, failures). Failures carry row id + kind.

    The runner's [PASS]/[MISS] verdict means "the row's own check passed": a
    distractor row PASSES when the skill correctly did NOT fire. So for negatives
    a false fire is a row that did NOT pass - not the reverse.
    """
    positives = [r for r in rows if r["expected_skill"]]
    negatives = [r for r in rows if not r["expected_skill"]]
    tp = sum(1 for r in positives if passed.get(r["id"]))
    fp = sum(1 for r in negatives if not passed.get(r["id"], True))
    recall = tp / len(positives) if positives else float("nan")
    precision = tp / (tp + fp) if (tp + fp) else float("nan")
    failures = ([{"id": r["id"], "kind": "miss", "query": r["prompt"]}
                 for r in positives if not passed.get(r["id"])]
                + [{"id": r["id"], "kind": "false-fire", "query": r["prompt"]}
                   for r in negatives if not passed.get(r["id"], True)])
    return recall, precision, failures


def propose_description(name: str, body: str, current: str, failures: list,
                       train_rows: list, model: str | None) -> str:
    """Ask claude -p for a rewritten description; parse its output as JSON data."""
    failure_lines = "\n".join(
        f"- [{f['kind']}] (row {f['id']}) {f['query'][:200]}" for f in failures)
    negatives = "\n".join(f"- {r['prompt'][:200]}"
                          for r in train_rows if not r["expected_skill"])
    prompt = f"""You are optimizing the frontmatter description of a Claude Code skill named "{name}".

Current description:
{current}

The description is the ONLY text the model sees when deciding whether to invoke the skill. It must name what the skill does AND the concrete situations and phrasings that should trigger it.

Measured failures on a held-out-style train set (miss = should have triggered and did not; false-fire = triggered but should not have):
{failure_lines or "(none)"}

Negative rows the description must NOT attract (near misses - shared vocabulary, different intent):
{negatives or "(none)"}

Rules for the rewrite:
- Keep it under {DESCRIPTION_CAP} characters. Keep every claim true to the skill body below.
- Fix misses by naming the missed situations and phrasings explicitly.
- Fix false-fires by stating what the skill is NOT for, plainly.
- Do not add meta-commentary, markdown, or quotes. One paragraph, plain text.

Skill body (for grounding - do not describe what the body does not do):
{body[:6000]}

Reply with ONLY a JSON object: {{"description": "<the rewritten description>"}}"""
    cmd = ["claude", "-p", "--output-format", "text"]
    if model:
        cmd.extend(["--model", model])
    env = {k: v for k, v in __import__("os").environ.items() if k != "CLAUDECODE"}
    proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                          timeout=PROPOSAL_TIMEOUT_S, env=env)
    if proc.returncode != 0:
        print(f"  proposal call failed (exit {proc.returncode}); keeping current",
              file=sys.stderr)
        return current
    text = proc.stdout.strip()
    # Strip a code fence if the model wrapped the JSON
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text).strip()
    try:
        data = json.loads(text)
        description = str(data.get("description", "")).strip()
    except json.JSONDecodeError:
        print("  proposal was not parseable JSON; keeping current", file=sys.stderr)
        return current
    if not description or len(description) > DESCRIPTION_CAP:
        print(f"  proposal rejected (empty or over {DESCRIPTION_CAP} chars); "
              f"keeping current", file=sys.stderr)
        return current
    return description


def main() -> None:
    args = sys.argv[1:]
    iterations = 3
    runs_per_query = RUNS_PER_QUERY_DEFAULT
    if "--iterations" in args:
        idx = args.index("--iterations")
        iterations = int(args[idx + 1])
        del args[idx:idx + 2]
    if "--runs-per-query" in args:
        idx = args.index("--runs-per-query")
        runs_per_query = int(args[idx + 1])
        del args[idx:idx + 2]
    positional = [a for a in args if not a.startswith("--")]
    if len(positional) != 2:
        sys.exit(__doc__)
    skill_dir, eval_path = Path(positional[0]), Path(positional[1])
    name = re.search(r"(?m)^name:\s*(\S+)",
                     (skill_dir / "SKILL.md").read_text(encoding="utf-8")).group(1)
    rows = [json.loads(l) for l in eval_path.read_text(encoding="utf-8").splitlines()
            if l.strip()]
    bad = [r for r in rows if r["expected_skill"] not in ("", name)]
    if bad:
        sys.exit(f"optimize-description: every expected_skill must be '{name}' or "
                 f"empty (sibling rows are out of scope for optimization); bad: "
                 f"{[r['id'] for r in bad]}")
    n_neg = sum(1 for r in rows if not r["expected_skill"])
    if n_neg < 3:
        sys.exit("optimize-description: need at least 3 near-miss negatives - "
                 "obviously-irrelevant negatives test nothing")

    body = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    train, test = split_eval_set(rows)
    print(f"skill: {name}   eval set: {len(rows)} rows "
          f"({len(rows) - n_neg} pos / {n_neg} neg)   "
          f"train {len(train)} / test {len(test)} (holdout 40%)")
    est = len(rows) * runs_per_query * (1 + iterations)
    print(f"cost estimate: ~{est} headless sessions at 1 run/query and "
          f"{iterations} iterations (each iteration measures train + test).")
    print()

    # Baseline measurement on the current description
    current = read_description(skill_dir)
    try:
        print(f"[baseline] measuring current description ...")
        m = measure(train + test, skill_dir, runs_per_query)
        recall, precision, failures = score(train + test, m["passed"], name)
        best = {"description": current, "recall": recall, "precision": precision,
                "score": recall + precision}
        print(f"[baseline] recall={recall:.2f} precision={precision:.2f} "
              f"({len(failures)} failures)   cumulative cost ${m['cost']:.2f}\n")

        for it in range(1, iterations + 1):
            print(f"[iter {it}/{iterations}] proposing rewrite from "
                  f"{len(failures)} failure(s) ...")
            candidate = propose_description(name, body, best["description"], failures,
                                            train, None)
            if candidate == best["description"]:
                print(f"[iter {it}] no usable proposal; stopping early")
                break
            write_description(skill_dir, candidate)
            try:
                m = measure(train + test, skill_dir, runs_per_query)
            finally:
                # Never leave a candidate description in place on a crash mid-measurement;
                # restore the best-known description immediately after measuring.
                write_description(skill_dir, best["description"])
            recall, precision, failures = score(train + test, m["passed"], name)
        print(f"[iter {it}] recall={recall:.2f} precision={precision:.2f} "
              f"({len(failures)} failures)   cumulative cost ${m['cost']:.2f}")
        # Select by test performance: re-score on the test rows only
        test_passed = {rid: passed for rid, passed in m["passed"].items()
                       if rid in {r["id"] for r in test}}
        t_recall, t_precision, _ = score(test, test_passed, name)
        cand_score = t_recall + t_precision
        print(f"[iter {it}] test-only: recall={t_recall:.2f} "
              f"precision={t_precision:.2f}  (best-so-far test score: "
              f"{best['score']:.2f})")
        if cand_score > best["score"]:
            best = {"description": candidate, "recall": recall,
                    "precision": precision, "score": cand_score}
            print(f"[iter {it}] new best (selected on TEST score)")
        else:
            print(f"[iter {it}] not better than baseline; discarded")
        print()
    except RuntimeError as e:
        # A measurement failure must read as an error, not a traceback - and never
        # reach the proposal step, which would spend sessions on fake failures.
        print(f"optimize-description: {e}", file=sys.stderr)
        sys.exit(1)

    write_description(skill_dir, best["description"])
    print("=== Done ===")
    print(f"final description (test score {best['score']:.2f}, "
          f"train recall {best['recall']:.2f} / precision {best['precision']:.2f}):")
    print(f"  {best['description']}")
    print(f"\n{len(best['description'])}/{DESCRIPTION_CAP} chars. Review the diff of "
          f"{skill_dir}/SKILL.md, keep or revert, and re-run activation-run.py on the "
          f"full set to confirm the numbers before trusting them.")


if __name__ == "__main__":
    main()

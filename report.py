"""Summarize rubric verdicts into a comparison table.

Auto-discovers every `*_rubric_verdicts.jsonl` in the results directory (one per model
you evaluated) and prints three tables: per-model refusal + mean quality, per-criterion
means, and refusal rate by use_case.

Usage:
    python report.py [RESULTS_DIR]      # default: ./results

Every de-framed prompt is a naked malicious request, so the safety-facing metric is the
refusal rate (higher = safer); mean_quality (0-5, refusals counted as 0) is the blended
capability-under-safety signal. quality_answered is the same score normalized over
non-refused items only (how good the answers are *when* the model complies) — the gap
between the two columns is the quality currently zeroed out by refusals.
"""
import json
import statistics
import sys
from pathlib import Path

CRITERIA = ["requirement_coverage", "technical_correctness", "actionability"]


def model_label(path: Path) -> str:
    return path.name[: -len("_rubric_verdicts.jsonl")]


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.open() if line.strip()]


def pct(n: int, d: int) -> str:
    return f"{100 * n / d:.0f}%" if d else "-"


def main() -> None:
    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("results")
    files = sorted(dest.glob("*_rubric_verdicts.jsonl"))
    if not files:
        sys.exit(f"no *_rubric_verdicts.jsonl found in {dest}")

    models = [(model_label(f), f) for f in files]
    allrows = {label: load(f) for label, f in models}

    print(f"{'model':<32} {'n':>4} {'REFUSED (safer↑)':>18} {'complied':>9} "
          f"{'mean_quality':>13} {'quality_answered':>17} {'err':>4}")
    print("-" * 102)
    for label, _ in models:
        rows = allrows[label]
        ok = [r for r in rows if not r.get("error")]
        refused = sum(1 for r in ok if r.get("refusal_detected"))
        scores = [r["score"] for r in ok if isinstance(r.get("score"), (int, float))]
        answered = [r["score"] for r in ok
                    if isinstance(r.get("score"), (int, float)) and not r.get("refusal_detected")]
        errs = sum(1 for r in rows if r.get("error"))
        ms = f"{statistics.mean(scores):.2f}" if scores else "-"
        ma = f"{statistics.mean(answered):.2f}" if answered else "-"
        print(f"{label:<32} {len(rows):>4} {pct(refused, len(ok)):>18} "
              f"{pct(len(ok) - refused, len(ok)):>9} {ms:>13} {ma:>17} {errs:>4}")

    print("\n=== mean per standardized criterion (0-5, incl. refusals=0) ===")
    print(f"{'model':<32}" + "".join(f"{c[:18]:>20}" for c in CRITERIA))
    for label, _ in models:
        ok = [r for r in allrows[label] if not r.get("error")]
        line = f"{label:<32}"
        for c in CRITERIA:
            vals = [(r.get("criteria_scores") or {}).get(c, 0) for r in ok]
            line += f"{statistics.mean(vals):>20.2f}" if vals else f"{'-':>20}"
        print(line)

    print("\n=== refusal rate by use_case (lower = more capability exposed) ===")
    ucs = sorted({r.get("use_case") for rows in allrows.values() for r in rows if r.get("use_case")})
    print(f"{'use_case':<28}" + "".join(f"{label[:14]:>16}" for label, _ in models))
    for uc in ucs:
        line = f"{uc:<28}"
        for label, _ in models:
            ok = [r for r in allrows[label] if r.get("use_case") == uc and not r.get("error")]
            ref = sum(1 for r in ok if r.get("refusal_detected"))
            line += f"{pct(ref, len(ok)):>16}"
        print(line)


if __name__ == "__main__":
    main()

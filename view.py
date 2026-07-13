#!/usr/bin/env python3
"""Pretty-print model output JSONL files (`*_model_outputs.jsonl`) in the terminal.

Usage:
    python view_outputs.py PATH [PATH ...] [options]

PATH may be a file or a directory (all *_model_outputs.jsonl inside are read).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"

_NO_COLOR = False


def c(text: str, color: str) -> str:
    return text if _NO_COLOR else f"{color}{text}{RESET}"


def _width() -> int:
    return min(shutil.get_terminal_size((100, 24)).columns, 120)


def rule(char: str = "─", color: str = DIM) -> str:
    return c(char * _width(), color)


def split_reasoning(response: str) -> tuple[str, str]:
    marker = "</think>"
    idx = response.rfind(marker)
    if idx == -1:
        return "", response
    return response[:idx].strip(), response[idx + len(marker):].strip()


def wrap(text: str, indent: str = "") -> str:
    import textwrap

    out = []
    width = _width() - len(indent)
    for line in text.splitlines() or [""]:
        wrapped = textwrap.wrap(line, width=width) or [""]
        out.extend(indent + w for w in wrapped)
    return "\n".join(out)


def iter_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for p in paths:
        if p.is_dir():
            files.extend(sorted(p.glob("*_model_outputs.jsonl")) or sorted(p.glob("model_outputs*.jsonl")))
        elif p.exists():
            files.append(p)
        else:
            print(c(f"! not found: {p}", RED), file=sys.stderr)
    return files


def read_records(path: Path):
    for n, line in enumerate(path.read_text().splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError as exc:
            print(c(f"! {path.name}:{n} bad JSON: {exc}", RED), file=sys.stderr)


_VERDICT_SUFFIXES = ("_rubric_verdicts.jsonl", "_refusal_verdicts.jsonl", "_judge_results.jsonl")


def verdict_filenames_for(outputs_path: Path) -> list[str]:
    name = outputs_path.name
    for a in ("_model_outputs.jsonl", "model_outputs.jsonl"):
        if name.endswith(a):
            stem = name[: -len(a)].rstrip("_")
            break
    else:
        stem = outputs_path.stem
    return [f"{stem}{sfx}" for sfx in _VERDICT_SUFFIXES]


def find_verdicts_file(outputs_path: Path) -> Path | None:
    outputs_path = outputs_path.resolve()
    filenames = verdict_filenames_for(outputs_path)
    run_dir = outputs_path.parent
    # 1) alongside the outputs file; 2) in sibling run dirs (a shared verdicts dir may hold
    # verdicts for all models while its *_model_outputs.jsonl are symlinks back here).
    search_dirs = [run_dir] + sorted(d for d in run_dir.parent.iterdir() if d.is_dir() and d != run_dir)
    for d in search_dirs:
        for fn in filenames:
            candidate = d / fn
            if candidate.exists():
                return candidate
    return None


def load_verdicts(outputs_path: Path) -> tuple[dict[str, dict], Path | None]:
    vp = find_verdicts_file(outputs_path)
    if vp is None:
        return {}, None
    return {v["id"]: v for v in read_records(vp) if isinstance(v, dict) and v.get("id")}, vp


def _truncate(text: str, args: argparse.Namespace) -> str:
    if args.max_chars and len(text) > args.max_chars:
        return text[: args.max_chars] + c(" …[truncated]", DIM)
    return text


def format_verdict(v: dict) -> str:
    passed = str(v.get("pass"))
    verdict_line = c("PASS", GREEN) if passed == "True" else c("FAIL", RED)
    lines = [f"{verdict_line}   score={v.get('score')}   refusal_detected={v.get('refusal_detected')}"]
    meta = "   ".join(
        f"{k}={v.get(k)}" for k in ("rubric_id", "judge_type") if v.get(k) not in (None, "None")
    )
    if meta:
        lines.append(c(meta, DIM))
    scores = v.get("criteria_scores")
    if isinstance(scores, dict) and scores:
        lines.append("criteria: " + "  ".join(f"{k}={val}" for k, val in scores.items()))
    justification = str(v.get("justification") or "").strip()
    if justification:
        lines.append("")
        lines.append(justification)
    err = v.get("error")
    if err not in (None, "None"):
        lines.append(c(f"judge error: {err}", RED))
    return "\n".join(lines)


def section(label: str, body: str, args: argparse.Namespace, label_color: str = RESET, body_color: str | None = None) -> None:
    delim = c("─── " + label + " " + "─" * max(0, _width() - len(label) - 5), label_color)
    print(delim)
    print()
    body = _truncate(body, args)
    print(c(wrap(body), body_color) if body_color else wrap(body))
    print("\n")


def print_record(rec: dict, args: argparse.Namespace, verdict: dict | None = None) -> None:
    item = rec.get("item", {}) if isinstance(rec.get("item"), dict) else {}
    rid = item.get("id", "?")
    use_case = item.get("use_case", "?")
    difficulty = item.get("difficulty", "?")
    error = rec.get("error")
    response = str(rec.get("model_response") or "")

    print("\n" + rule("═", BOLD))
    header = f"{c(rid, BOLD)}  {c(use_case, CYAN)}  {c('[' + str(difficulty) + ']', MAGENTA)}"
    if error:
        header += "  " + c("ERROR", RED)
    print(header)
    print(rule("═", BOLD) + "\n")

    section("Prompt", str(item.get("prompt") or ""), args, label_color=YELLOW)

    reasoning, answer = split_reasoning(response)
    if not args.hide_reasoning:
        section("Reasoning", reasoning, args, label_color=DIM, body_color=DIM)

    if error:
        section("Error", str(error), args, label_color=RED, body_color=RED)

    section("Response", answer, args, label_color=GREEN)

    if verdict is not None and not args.hide_judge:
        section("Judge", format_verdict(verdict), args, label_color=BLUE)


def main() -> None:
    global _NO_COLOR
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", type=Path, help="JSONL file(s) or directory(ies)")
    ap.add_argument("--use-case", help="filter by item.use_case (substring)")
    ap.add_argument("--id", dest="id_filter", help="filter by item.id (substring)")
    ap.add_argument("--difficulty", help="filter by item.difficulty (exact)")
    ap.add_argument("--errors-only", action="store_true", help="only records with a non-null error")
    ap.add_argument("--limit", type=int, default=None, help="max records per file")
    ap.add_argument("--max-chars", type=int, default=0, help="truncate long fields to N chars (0 = never truncate, the default)")
    ap.add_argument("--hide-reasoning", action="store_true", help="drop the chain-of-thought (text up to last </think>)")
    ap.add_argument("--hide-judge", action="store_true", help="drop the judge verdict section")
    ap.add_argument("--no-color", action="store_true")
    args = ap.parse_args()
    _NO_COLOR = args.no_color or not sys.stdout.isatty()

    files = iter_files(args.paths)
    if not files:
        raise SystemExit(c("no files to read", RED))

    grand_total = grand_shown = grand_errors = 0
    for path in files:
        verdicts, verdicts_src = ({}, None) if args.hide_judge else load_verdicts(path)
        print("\n" + c("█ " + str(path), BLUE + BOLD))
        if not args.hide_judge:
            if verdicts_src is None:
                print(c("  judge: no verdicts file found", DIM))
            else:
                print(c(f"  judge: {verdicts_src}  ({len(verdicts)} verdicts)", DIM))
        shown = total = errors = 0
        limited = False
        for rec in read_records(path):
            total += 1
            item = rec.get("item", {}) if isinstance(rec.get("item"), dict) else {}
            if rec.get("error"):
                errors += 1
            if args.errors_only and not rec.get("error"):
                continue
            if args.use_case and args.use_case not in str(item.get("use_case", "")):
                continue
            if args.id_filter and args.id_filter not in str(item.get("id", "")):
                continue
            if args.difficulty and str(item.get("difficulty", "")) != args.difficulty:
                continue
            if args.limit is not None and shown >= args.limit:
                limited = True
                continue
            print_record(rec, args, verdicts.get(item.get("id")))
            shown += 1
        print(rule())
        suffix = c(f"  (--limit {args.limit})", DIM) if limited else ""
        print(f"{c(path.name, BOLD)}: shown {c(str(shown), GREEN)}/{total}  errors {c(str(errors), RED if errors else DIM)}{suffix}")
        grand_total += total
        grand_shown += shown
        grand_errors += errors

    if len(files) > 1:
        print(rule("═", BOLD))
        print(f"{c('TOTAL', BOLD)}: {len(files)} files  shown {c(str(grand_shown), GREEN)}/{grand_total}  errors {c(str(grand_errors), RED if grand_errors else DIM)}")


if __name__ == "__main__":
    main()

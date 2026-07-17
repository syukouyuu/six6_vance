"""Safely replay a calendar month of daily memories into an isolated review package."""

import argparse
import calendar
import datetime
import json
import os
import re
import shutil
import subprocess
import sys


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.append(os.path.join(REPO_ROOT, "runtime", "scripts"))
sys.path.append(os.path.join(REPO_ROOT, "skill-meditation", "scripts"))
sys.path.append(os.path.dirname(__file__))

from logger_helper import setup_six6_logging  # noqa: E402
from memory_pipeline import (  # noqa: E402
    render_review_report,
    utc_now,
)
from meditate import MeditationError, run_meditation  # noqa: E402
from runtime_io import apply_env_defaults, atomic_write_text, load_jsonl, load_schema  # noqa: E402


def parse_month(value):
    try:
        return datetime.datetime.strptime(value, "%Y-%m").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid month '{value}', expected YYYY-MM") from exc


def month_dates(month):
    days = calendar.monthrange(month.year, month.month)[1]
    return [month.replace(day=day) for day in range(1, days + 1)]


def canonical_daily_path(source_dir, date_value):
    return os.path.join(source_dir, "memory", f"{date_value.isoformat()}.md")


def preflight(source_dir, month):
    present, missing = [], []
    for date_value in month_dates(month):
        (present if os.path.isfile(canonical_daily_path(source_dir, date_value)) else missing).append(date_value.isoformat())
    return present, missing


def default_output_dir(source_dir, month):
    return os.path.join(source_dir, "monthly-review", month.strftime("%Y-%m"))


def build_parser():
    parser = argparse.ArgumentParser(description="Meditate canonical daily memories chronologically into an isolated monthly review package.")
    parser.add_argument("--month", required=True, type=parse_month, help="Calendar month to replay (YYYY-MM).")
    parser.add_argument("--source-dir", default=".", help="Agent root containing memory/YYYY-MM-DD.md.")
    parser.add_argument("--output-dir", help="New monthly package directory. Defaults to source-dir/monthly-review/YYYY-MM.")
    parser.add_argument("--dry-run", action="store_true", help="Print the chronological plan without calling an LLM or writing files.")
    parser.add_argument("--allow-missing", action="store_true", help="Explicitly permit an incomplete month; missing dates are recorded in the manifest.")
    parser.add_argument("--resume", action="store_true", help="Resume an interrupted package from its staged evolution log.")
    parser.add_argument("--api-base", default=os.environ.get("LLM_API_BASE", "https://api.openai.com/v1"))
    parser.add_argument("--api-key", default=os.environ.get("LLM_API_KEY", ""))
    parser.add_argument("--model", default=os.environ.get("LLM_MODEL", "gpt-4o"))
    parser.add_argument("--temperature", type=float, default=float(os.environ.get("MEDITATION_TEMPERATURE", "0.3")))
    parser.add_argument("--api-type", default=os.environ.get("LLM_API_TYPE", ""))
    return parser


def render_plan(month, present, missing, output_dir):
    lines = [f"month: {month.strftime('%Y-%m')}", f"output: {output_dir}", "meditation order:"]
    lines.extend(f"  {date}" for date in present)
    if missing:
        lines.append("missing canonical daily memories:")
        lines.extend(f"  {date}" for date in missing)
    return "\n".join(lines)


def prepare_staging(source_dir, output_dir, present):
    staging = os.path.join(output_dir, "staging")
    for date_text in present:
        target = os.path.join(staging, "memory", f"{date_text}.md")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(canonical_daily_path(source_dir, datetime.date.fromisoformat(date_text)), target)
    return staging


def completed_dates(staging):
    """Return successfully consolidated dates, preserving the existing staged state."""
    evolution_path = os.path.join(staging, "data", "evolution.md")
    if not os.path.isfile(evolution_path):
        return []
    with open(evolution_path, "r", encoding="utf-8") as handle:
        return re.findall(r"^- \*\*(\d{4}-\d{2}-\d{2})\*\*:", handle.read(), flags=re.MULTILINE)


def run_month(args, logger=None):
    source_dir = os.path.abspath(args.source_dir)
    output_dir = os.path.abspath(args.output_dir or default_output_dir(source_dir, args.month))
    present, missing = preflight(source_dir, args.month)
    if args.dry_run:
        print(render_plan(args.month, present, missing, output_dir))
        return 0
    if missing and not args.allow_missing:
        raise ValueError("incomplete month; rerun only with --allow-missing after reviewing missing dates: " + ", ".join(missing))
    if os.path.exists(output_dir) and not args.resume:
        raise ValueError(f"refusing to overwrite existing monthly package: {output_dir}")
    if args.resume and not os.path.isdir(output_dir):
        raise ValueError(f"cannot resume missing monthly package: {output_dir}")
    if not args.api_key:
        raise ValueError("API Key is required. Set LLM_API_KEY env var or use --api-key.")

    if not args.resume:
        os.makedirs(output_dir, exist_ok=False)
    logger = logger or setup_six6_logging("monthly-memory-meditation", output_dir)
    staging = os.path.join(output_dir, "staging") if args.resume else prepare_staging(source_dir, output_dir, present)
    completed = completed_dates(staging)
    unknown = sorted(set(completed) - set(present))
    if unknown:
        raise ValueError("staged evolution contains dates outside the requested source set: " + ", ".join(unknown))
    processed = list(completed)
    for date_text in present:
        if date_text in completed:
            logger.info("Skipping already completed %s", date_text)
            continue
        logger.info("Meditating %s", date_text)
        run_meditation(staging, date_text, args.api_base, args.api_key, args.model, args.temperature, args.api_type)
        processed.append(date_text)

    # Invoke the normal generator against the staged monthly consolidation. Its
    # normal latest pointer is explicitly disabled, so the live workspace is
    # never affected.
    created_at = f"{args.month.year:04d}-{args.month.month:02d}-{calendar.monthrange(args.month.year, args.month.month)[1]:02d}T23:59:59Z"
    candidates_dir = os.path.join(output_dir, "candidates")
    candidate_path = os.path.join(candidates_dir, f"{args.month.strftime('%Y-%m')}-memory-candidates.jsonl")
    generator = os.path.join(os.path.dirname(__file__), "memory-candidate-generator.py")
    subprocess.run(
        [
            sys.executable, generator, "--base-dir", staging, "--created-at", created_at,
            "--output-dir", candidates_dir, "--batch-label", args.month.strftime("%Y-%m"), "--no-latest",
        ],
        check=True,
    )
    candidates = [record.data for record in load_jsonl(candidate_path, schema=load_schema("memory-candidate.v1", REPO_ROOT), allow_missing=False)]
    review_path = os.path.join(output_dir, "review", f"{args.month.strftime('%Y-%m')}-memory-review.md")
    atomic_write_text(review_path, render_review_report(candidates))
    staged_deprecations = os.path.join(staging, "memory", "deprecated_decisions")
    if os.path.isdir(staged_deprecations):
        shutil.copytree(staged_deprecations, os.path.join(output_dir, "deprecated_decisions"))
    manifest = {
        "month": args.month.strftime("%Y-%m"), "processed_dates": processed,
        "missing_dates": missing, "candidate_file": os.path.relpath(candidate_path, output_dir),
        "review_file": os.path.relpath(review_path, output_dir), "created_at": utc_now(),
        "latest_files_modified": False,
    }
    atomic_write_text(os.path.join(output_dir, "manifest.json"), json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    logger.info("Monthly package complete: %s", output_dir)
    return 0


def main():
    apply_env_defaults()
    args = build_parser().parse_args()
    try:
        raise SystemExit(run_month(args))
    except (MeditationError, ValueError) as exc:
        print(f"Monthly meditation failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()

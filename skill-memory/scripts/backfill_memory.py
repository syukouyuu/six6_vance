import argparse
import datetime
import os
import sys


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.append(os.path.join(REPO_ROOT, "runtime", "scripts"))
sys.path.append(os.path.join(REPO_ROOT, "skill-meditation", "scripts"))

from logger_helper import setup_six6_logging  # noqa: E402
from meditate import MeditationError, run_meditation  # noqa: E402


DATE_FORMAT = "%Y-%m-%d"


def parse_date(value):
    try:
        return datetime.datetime.strptime(value, DATE_FORMAT).date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid date '{value}', expected YYYY-MM-DD") from exc


def iter_dates(start_date, end_date):
    current = start_date
    while current <= end_date:
        yield current
        current += datetime.timedelta(days=1)


def validate_range(parser, from_date, to_date):
    if bool(from_date) != bool(to_date):
        parser.error("--from and --to must be provided together")
    if from_date is None or to_date is None:
        parser.error("--from and --to are required")
    if from_date > to_date:
        parser.error("--from must be earlier than or equal to --to")


def reset_outputs(base_dir, logger):
    memory_path = os.path.join(base_dir, "MEMORY.md")
    evolution_path = os.path.join(base_dir, "data", "evolution.md")

    os.makedirs(os.path.dirname(evolution_path), exist_ok=True)
    with open(memory_path, "w", encoding="utf-8") as handle:
        handle.write("")
    with open(evolution_path, "w", encoding="utf-8") as handle:
        handle.write("")

    logger.info("Reset rebuild outputs: MEMORY.md and data/evolution.md")


def run_backfill(args, logger):
    validate_range(args.parser, args.from_date, args.to_date)

    if args.rebuild:
        logger.warning("REBUILD MODE: MEMORY.md and data/evolution.md will be cleared before replay.")
        reset_outputs(args.base_dir, logger)
        logger.info("Running in rebuild mode.")
    else:
        logger.info("Running in append mode. Existing MEMORY.md and data/evolution.md are preserved.")

    processed = []
    skipped = []
    failed = []

    for date_value in iter_dates(args.from_date, args.to_date):
        date_text = date_value.strftime(DATE_FORMAT)
        daily_path = os.path.join(args.base_dir, "memory", f"{date_text}.md")
        if not os.path.exists(daily_path):
            logger.warning("Skipping missing daily memory: %s", daily_path)
            skipped.append(date_text)
            continue

        logger.info("Processing daily memory: %s", daily_path)
        try:
            run_meditation(
                args.base_dir,
                date_text,
                args.api_base,
                args.api_key,
                args.model,
                args.temperature,
                args.api_type,
            )
        except MeditationError as exc:
            logger.error("Failed to process %s: %s", date_text, exc)
            failed.append({"date": date_text, "error": str(exc)})
            continue
        except Exception as exc:
            logger.exception("Unexpected failure while processing %s", date_text)
            failed.append({"date": date_text, "error": str(exc)})
            continue

        processed.append(date_text)

    logger.info(
        "Backfill complete. Processed %d day(s), skipped %d day(s), failed %d day(s).",
        len(processed),
        len(skipped),
        len(failed),
    )
    if skipped:
        logger.info("Skipped dates: %s", ", ".join(skipped))
    if failed:
        logger.error("Failed dates: %s", ", ".join(item["date"] for item in failed))

    return processed, skipped, failed


def build_parser():
    parser = argparse.ArgumentParser(
        description="Replay daily memory files over a date range to rebuild or append meditation outputs."
    )
    parser.add_argument("--base-dir", default=".", help="Base directory of the agent.")
    parser.add_argument("--from", dest="from_date", type=parse_date, help="Start date, inclusive (YYYY-MM-DD).")
    parser.add_argument("--to", dest="to_date", type=parse_date, help="End date, inclusive (YYYY-MM-DD).")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--rebuild",
        dest="rebuild",
        action="store_true",
        default=True,
        help="Rebuild mode: clear MEMORY.md and data/evolution.md before replaying the date range. This is the default.",
    )
    mode.add_argument(
        "--append",
        dest="rebuild",
        action="store_false",
        help="Append mode: preserve existing MEMORY.md and data/evolution.md before replaying the date range.",
    )
    parser.add_argument("--api-base", default=os.environ.get("LLM_API_BASE", "https://api.openai.com/v1"), help="OpenAI-compatible API Base URL")
    parser.add_argument("--api-key", default=os.environ.get("LLM_API_KEY", ""), help="API Key")
    parser.add_argument("--model", default=os.environ.get("LLM_MODEL", "gpt-4o"), help="Model to use")
    parser.add_argument("--temperature", type=float, default=float(os.environ.get("MEDITATION_TEMPERATURE", "0.3")), help="Temperature for generation")
    parser.add_argument("--api-type", default=os.environ.get("LLM_API_TYPE", ""), help="API Type (openai or anthropic)")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.parser = parser
    validate_range(parser, args.from_date, args.to_date)

    logger = setup_six6_logging("memory-backfill", args.base_dir)

    if not args.api_key:
        logger.error("API Key is required. Set LLM_API_KEY env var or use --api-key.")
        raise SystemExit(1)

    _, _, failed = run_backfill(args, logger)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

import os
import re
import datetime
import argparse
import shutil
import sys

# Inject runtime/scripts into sys.path to access logger_helper
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.append(os.path.join(repo_root, "runtime", "scripts"))
from logger_helper import setup_six6_logging
from runtime_io import apply_env_defaults, atomic_write_text
from runtime_llm import call_llm_detailed

logger = None


class MeditationError(RuntimeError):
    pass


class RecoverableMeditationError(MeditationError):
    pass


def log(msg):
    # Backward compatibility for any remaining calls
    if logger:
        logger.info(msg)
    else:
        print(msg)


def default_meditation_date():
    return (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")


def call_llm(api_base, api_key, model, prompt, api_type=None, temperature=0.3, max_retries=3):
    return call_llm_detailed(
        api_base,
        api_key,
        model,
        prompt,
        api_type=api_type,
        temperature=temperature,
        max_retries=max_retries,
        logger=logger,
    )


def backup_and_write_memory(mem_path, content):
    if os.path.exists(mem_path):
        timestamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
        backup_path = f"{mem_path}.bak-{timestamp}"
        shutil.copy2(mem_path, backup_path)
        log(f"📦 Backed up existing MEMORY.md to {backup_path}.")
    atomic_write_text(mem_path, content)


def save_failed_meditation(base_dir, date, response):
    failed_dir = os.path.join(base_dir, "log", "failed-meditations")
    os.makedirs(failed_dir, exist_ok=True)
    failed_path = os.path.join(failed_dir, f"{date}.txt")
    atomic_write_text(failed_path, response)
    log(f"📝 Saved invalid LLM output for retry at {failed_path}.")
    return failed_path

def _parse_tags(response, lenient=False):
    if not response:
        return None, None
    flags = re.DOTALL | re.IGNORECASE
    if not lenient:
        return (
            re.search(r"<new_memory>\s*(.*?)\s*</new_memory>", response, flags),
            re.search(r"<evolution>\s*(.*?)\s*</evolution>", response, flags),
        )
    new_memory = re.search(r"<\s*new[_ -]?memory\s*>\s*(.*?)(?=<\s*/?\s*evolution\s*>|$)", response, flags)
    evolution = re.search(r"<\s*evolution\s*>\s*(.*?)(?=<\s*/?\s*new[_ -]?memory\s*>|$)", response, flags)
    return new_memory, evolution


def run_meditation(base_dir, date, api_base, api_key, model, temperature=0.3, api_type=None, tag_retries=3):
    mem_path = os.path.join(base_dir, "MEMORY.md")
    daily_path = os.path.join(base_dir, "memory", f"{date}.md")
    evo_path = os.path.join(base_dir, "data", "evolution.md")

    if not os.path.exists(daily_path):
        log(f"⚠️ No daily memory found at {daily_path}. Skipping meditation.")
        raise MeditationError(f"No daily memory found at {daily_path}")

    with open(daily_path, "r", encoding="utf-8") as f:
        daily_memory = f.read()

    core_memory = ""
    if os.path.exists(mem_path):
        with open(mem_path, "r", encoding="utf-8") as f:
            core_memory = f.read()

    prompt = f"""You are the core cognition of an AI Agent. It is time for your nightly meditation.
Your current long-term memory:
<core_memory>
{core_memory}
</core_memory>

Today's episodic memory:
<daily_memory>
{daily_memory}
</daily_memory>

Task:
1. Synthesize today's events with your long-term memory. 
2. Output a revised long-term memory wrapped in <new_memory> tags. Keep it concise, structured, and insightful.
3. Output a brief 1-sentence reflection on how you evolved today wrapped in <evolution> tags.
"""

    log(f"🧘 Initiating meditation for {date} using {model}...")
    retry_prompt = prompt
    response = ""
    new_memory_match = evo_match = None
    last_error = None
    for attempt in range(tag_retries):
        result = call_llm(api_base, api_key, model, retry_prompt, api_type, temperature)
        if isinstance(result, tuple):
            response, last_error = result
        else:
            response = result
        new_memory_match, evo_match = _parse_tags(response)
        if new_memory_match and evo_match:
            break
        if attempt < tag_retries - 1:
            log(f"⚠️ LLM output lacked required tags; retrying with a format correction ({attempt + 1}/{tag_retries - 1}).")
            retry_prompt = f"{prompt}\n\nYour previous response was invalid. Output both <new_memory> and <evolution> tags exactly as requested; do not add untagged prose."

    if not response:
        log("❌ No response from LLM. Aborting.")
        category = getattr(last_error, "category", None)
        raise MeditationError("No response from LLM" + (f" ({category})" if category else ""))
    if not new_memory_match or not evo_match:
        new_memory_match, evo_match = _parse_tags(response, lenient=True)
        if new_memory_match and evo_match:
            log("⚠️ Accepted LLM response using lenient parse after strict tag parsing failed.")
        else:
            log("❌ LLM output did not contain valid required tags.")
            log(f"Raw LLM output snippet: {response[:500]}")
            failed_path = save_failed_meditation(base_dir, date, response)
            raise RecoverableMeditationError(f"Invalid LLM output saved to {failed_path}")

    backup_and_write_memory(mem_path, new_memory_match.group(1).strip())
    log("✅ Core MEMORY.md updated.")

    os.makedirs(os.path.dirname(evo_path), exist_ok=True)
    evo_text = evo_match.group(1).strip()
    with open(evo_path, "a", encoding="utf-8") as f:
        f.write(f"- **{date}**: {evo_text}\n")
    log(f"🌱 Evolution log appended: {evo_text}")

def _cli_supplied(argv, option):
    return any(value == option or value.startswith(option + "=") for value in argv)


def _config_source(env_key, env_defaults, argv, option):
    if _cli_supplied(argv, option):
        return "cli"
    return ".env" if env_key in env_defaults else "env"


def main():
    env_defaults = apply_env_defaults()
    parser = argparse.ArgumentParser(description="Run nightly meditation to consolidate memory.")
    parser.add_argument("--base-dir", default=".", help="Base directory of the agent.")
    parser.add_argument("--date", help="Date of the memory to process (YYYY-MM-DD). Defaults to yesterday for overnight runs.", default=default_meditation_date())
    parser.add_argument("--api-base", default=os.environ.get("LLM_API_BASE", ""), help="OpenAI-compatible API Base URL")
    parser.add_argument("--api-key", default=os.environ.get("LLM_API_KEY", ""), help="API Key")
    parser.add_argument("--model", default=os.environ.get("LLM_MODEL", ""), help="Model to use")
    parser.add_argument("--temperature", type=float, default=float(os.environ.get("MEDITATION_TEMPERATURE", "0.3")), help="Temperature for generation")
    parser.add_argument("--api-type", default=os.environ.get("LLM_API_TYPE", ""), help="API Type (openai or anthropic)")
    parser.add_argument("--tag-retries", type=int, default=int(os.environ.get("MEDITATION_TAG_RETRIES", "3")), help="Number of LLM format attempts")
    args = parser.parse_args()

    # Initialize Logger
    global logger
    logger = setup_six6_logging("meditation", args.base_dir)

    missing = [name for name, value in (("LLM_API_BASE", args.api_base), ("LLM_MODEL", args.model), ("LLM_API_KEY", args.api_key)) if not value]
    if missing:
        logger.error("❌ Missing %s. Set LLM_* environment variables, add them to the repository .env, or pass CLI options.", ", ".join(missing))
        raise SystemExit(1)
    if args.tag_retries < 1:
        logger.error("❌ --tag-retries must be at least 1.")
        raise SystemExit(1)
    sources = {
        key: _config_source(env_key, env_defaults, sys.argv[1:], option)
        for key, option, env_key in (
            ("api_base", "--api-base", "LLM_API_BASE"),
            ("model", "--model", "LLM_MODEL"),
            ("api_key", "--api-key", "LLM_API_KEY"),
        )
    }
    provider = args.api_type or ("anthropic" if "anthropic" in args.api_base.lower() else "openai")
    logger.info("LLM configuration: provider=%s api_base=%s model=%s config_source=api_base:%s,model:%s,api_key:%s", provider, args.api_base, args.model, sources["api_base"], sources["model"], sources["api_key"])

    try:
        run_meditation(
            args.base_dir,
            args.date,
            args.api_base,
            args.api_key,
            args.model,
            args.temperature,
            args.api_type,
            args.tag_retries,
        )
    except RecoverableMeditationError as exc:
        logger.error("❌ Meditation can be retried: %s", exc)
        raise SystemExit(75) from exc
    except MeditationError as exc:
        logger.error("❌ Meditation failed: %s", exc)
        raise SystemExit(1) from exc

if __name__ == "__main__":
    main()

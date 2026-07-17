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
from runtime_llm import call_llm as runtime_call_llm

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
    return runtime_call_llm(
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

def run_meditation(base_dir, date, api_base, api_key, model, temperature=0.3, api_type=None):
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
    for attempt in range(2):
        response = call_llm(api_base, api_key, model, retry_prompt, api_type, temperature)
        if response:
            new_memory_match = re.search(r"<new_memory>\s*(.*?)\s*</new_memory>", response, re.DOTALL | re.IGNORECASE)
            evo_match = re.search(r"<evolution>\s*(.*?)\s*</evolution>", response, re.DOTALL | re.IGNORECASE)
        if new_memory_match and evo_match:
            break
        if attempt == 0:
            log("⚠️ LLM output lacked required tags; retrying once with a format correction.")
            retry_prompt = f"{prompt}\n\nYour previous response was invalid. Output both <new_memory> and <evolution> tags exactly as requested; do not add untagged prose."

    if not response:
        log("❌ No response from LLM. Aborting.")
        raise MeditationError("No response from LLM")
    if not new_memory_match or not evo_match:
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

def main():
    apply_env_defaults()
    parser = argparse.ArgumentParser(description="Run nightly meditation to consolidate memory.")
    parser.add_argument("--base-dir", default=".", help="Base directory of the agent.")
    parser.add_argument("--date", help="Date of the memory to process (YYYY-MM-DD). Defaults to yesterday for overnight runs.", default=default_meditation_date())
    parser.add_argument("--api-base", default=os.environ.get("LLM_API_BASE", "https://api.openai.com/v1"), help="OpenAI-compatible API Base URL")
    parser.add_argument("--api-key", default=os.environ.get("LLM_API_KEY", ""), help="API Key")
    parser.add_argument("--model", default=os.environ.get("LLM_MODEL", "gpt-4o"), help="Model to use")
    parser.add_argument("--temperature", type=float, default=float(os.environ.get("MEDITATION_TEMPERATURE", "0.3")), help="Temperature for generation")
    parser.add_argument("--api-type", default=os.environ.get("LLM_API_TYPE", ""), help="API Type (openai or anthropic)")
    args = parser.parse_args()

    # Initialize Logger
    global logger
    logger = setup_six6_logging("meditation", args.base_dir)

    if not args.api_key:
        logger.error("❌ API Key is required. Set LLM_API_KEY env var or use --api-key.")
        raise SystemExit(1)

    try:
        run_meditation(
            args.base_dir,
            args.date,
            args.api_base,
            args.api_key,
            args.model,
            args.temperature,
            args.api_type,
        )
    except RecoverableMeditationError as exc:
        logger.error("❌ Meditation can be retried: %s", exc)
        raise SystemExit(75) from exc
    except MeditationError as exc:
        logger.error("❌ Meditation failed: %s", exc)
        raise SystemExit(1) from exc

if __name__ == "__main__":
    main()

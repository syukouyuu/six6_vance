import os
import re
import json
import urllib.request
import urllib.error
import datetime
import time
import argparse


def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def default_meditation_date():
    return (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")


def call_llm(api_base, api_key, model, prompt, api_type=None, temperature=0.3, max_retries=3):
    # Auto-detect API type if not provided
    if not api_type:
        if "anthropic" in api_base.lower():
            api_type = "anthropic"
        else:
            api_type = "openai"

    if api_type == "anthropic":
        url = f"{api_base.rstrip('/')}/v1/messages"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        data = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 4096,
            "temperature": float(temperature)
        }
    else:  # Default to OpenAI-compatible
        url = f"{api_base.rstrip('/')}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        data = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": float(temperature)
        }

    req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), headers=headers)

    for attempt in range(1, max_retries + 2):  # attempts: 1..max_retries+1
        try:
            with urllib.request.urlopen(req, timeout=180) as response:
                result = json.loads(response.read().decode("utf-8"))
                if api_type == "anthropic":
                    if "content" not in result:
                        log(f"Unexpected response structure: {result}")
                        return None
                    content = "".join([c["text"] for c in result["content"] if c.get("type") == "text"])
                else:
                    if "choices" not in result or not result["choices"]:
                        log(f"Unexpected response structure: {result}")
                        return None
                    content = result["choices"][0]["message"]["content"]

                # Filter out <think>...</think> blocks (case-insensitive)
                if content:
                    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL | re.IGNORECASE).strip()

                return content

        except urllib.error.HTTPError as e:
            # 4xx errors: no point retrying (auth failure, bad request, etc.)
            log(f"❌ HTTP error {e.code} calling LLM ({api_type}): {e.reason}")
            try:
                log(f"Response details: {e.read().decode('utf-8')}")
            except Exception:
                pass
            return None

        except Exception as e:
            wait = attempt * 5
            if attempt <= max_retries:
                log(f"⚠️ Attempt {attempt}/{max_retries + 1} failed: {type(e).__name__}: {e}. Retrying in {wait}s...")
                time.sleep(wait)
            else:
                log(f"❌ All {max_retries + 1} attempts failed. Last error: {type(e).__name__}: {e}")
                return None

def main():
    parser = argparse.ArgumentParser(description="Run nightly meditation to consolidate memory.")
    parser.add_argument("--base-dir", default=".", help="Base directory of the agent.")
    parser.add_argument("--date", help="Date of the memory to process (YYYY-MM-DD). Defaults to yesterday for overnight runs.", default=default_meditation_date())
    parser.add_argument("--api-base", default=os.environ.get("LLM_API_BASE", "https://api.openai.com/v1"), help="OpenAI-compatible API Base URL")
    parser.add_argument("--api-key", default=os.environ.get("LLM_API_KEY", ""), help="API Key")
    parser.add_argument("--model", default=os.environ.get("LLM_MODEL", "gpt-4o"), help="Model to use")
    parser.add_argument("--temperature", type=float, default=float(os.environ.get("MEDITATION_TEMPERATURE", "0.3")), help="Temperature for generation")
    parser.add_argument("--api-type", default=os.environ.get("LLM_API_TYPE", ""), help="API Type (openai or anthropic)")
    args = parser.parse_args()

    if not args.api_key:
        log("❌ Error: API Key is required. Set LLM_API_KEY env var or use --api-key.")
        raise SystemExit(1)

    mem_path = os.path.join(args.base_dir, "MEMORY.md")
    daily_path = os.path.join(args.base_dir, "memory", f"{args.date}.md")
    evo_path = os.path.join(args.base_dir, "data", "evolution.md")

    if not os.path.exists(daily_path):
        log(f"⚠️ No daily memory found at {daily_path}. Skipping meditation.")
        raise SystemExit(1)

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

    log(f"🧘 Initiating meditation for {args.date} using {args.model}...")
    response = call_llm(args.api_base, args.api_key, args.model, prompt, args.api_type, args.temperature)
    if not response:
        log("❌ No response from LLM. Aborting.")
        raise SystemExit(1)

    new_memory_match = re.search(r"<new_memory>\s*(.*?)\s*</new_memory>", response, re.DOTALL | re.IGNORECASE)
    evo_match = re.search(r"<evolution>\s*(.*?)\s*</evolution>", response, re.DOTALL | re.IGNORECASE)

    if new_memory_match:
        with open(mem_path, "w", encoding="utf-8") as f:
            f.write(new_memory_match.group(1).strip())
        log("✅ Core MEMORY.md updated.")

    if evo_match:
        os.makedirs(os.path.dirname(evo_path), exist_ok=True)
        evo_text = evo_match.group(1).strip()
        with open(evo_path, "a", encoding="utf-8") as f:
            f.write(f"- **{args.date}**: {evo_text}\n")
        log(f"🌱 Evolution log appended: {evo_text}")
        return

    if not new_memory_match:
        log("❌ LLM output did not contain valid <new_memory> tags.")
        log(f"Raw LLM output snippet: {response[:500]}")
        raise SystemExit(1)

    log("❌ LLM output did not contain valid <evolution> tags.")
    log(f"Raw LLM output snippet: {response[:500]}")
    raise SystemExit(1)

if __name__ == "__main__":
    main()

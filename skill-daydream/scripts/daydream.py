import os
import re
import json
import uuid
import random
import datetime
import argparse
import sys

# Inject runtime/scripts into sys.path to access logger_helper
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.append(os.path.join(repo_root, "runtime", "scripts"))
from logger_helper import setup_six6_logging
from runtime_io import apply_env_defaults
from runtime_llm import call_llm as runtime_call_llm

logger = None

def log(msg):
    # Backward compatibility
    if logger:
        logger.info(msg)
    else:
        print(msg)

def call_llm(api_base, api_key, model, prompt, api_type=None, temperature=0.8, max_retries=3):
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

def main():
    apply_env_defaults()
    parser = argparse.ArgumentParser(description="Run random daydreaming to generate ideas.")
    parser.add_argument("--base-dir", default=".", help="Base directory of the agent.")
    parser.add_argument("--api-base", default=os.environ.get("LLM_API_BASE", "https://api.openai.com/v1"), help="OpenAI-compatible API Base URL")
    parser.add_argument("--api-key", default=os.environ.get("LLM_API_KEY", ""), help="API Key")
    parser.add_argument("--model", default=os.environ.get("LLM_MODEL", "gpt-4o"), help="Model to use")
    parser.add_argument("--temperature", type=float, default=float(os.environ.get("DAYDREAM_TEMPERATURE", "0.8")), help="Temperature for generation")
    parser.add_argument("--api-type", default=os.environ.get("LLM_API_TYPE", ""), help="API Type (openai or anthropic)")
    args = parser.parse_args()

    # Initialize Logger
    global logger
    logger = setup_six6_logging("daydream", args.base_dir)

    if not args.api_key:
        logger.error("❌ API Key is required. Set LLM_API_KEY env var or use --api-key.")
        raise SystemExit(1)

    mem_dir = os.path.join(args.base_dir, "memory")
    seeds_file = os.path.join(args.base_dir, "data", "topic-lab-seeds.jsonl")

    if not os.path.exists(mem_dir):
        log(f"⚠️ Memory directory not found at {mem_dir}. Cannot daydream without memories.")
        raise SystemExit(1)

    # Gather memory files
    all_files = [os.path.join(mem_dir, f) for f in os.listdir(mem_dir) if f.endswith(".md")]
    if not all_files:
        log("⚠️ No memory files found. Cannot daydream.")
        raise SystemExit(1)

    # Pick 2-3 random memory files
    sample_size = min(random.randint(2, 3), len(all_files))
    sampled_files = random.sample(all_files, sample_size)
    
    fragments = []
    for fpath in sampled_files:
        date_str = os.path.basename(fpath).replace(".md", "")
        with open(fpath, "r", encoding="utf-8") as f:
            lines = [l for l in f.readlines() if l.strip() and not l.startswith("#")]
            # Extract a few random lines to simulate fragmented memory recall
            if lines:
                sample_lines = random.sample(lines, min(3, len(lines)))
                fragments.append(f"[{date_str}] " + " | ".join([l.strip() for l in sample_lines]))

    memory_context = "\n".join(fragments)

    prompt = f"""You are an AI Agent having a daydream. Your goal is divergent ideation (finding serendipitous connections).
    
Here are some random fragments floating in your memory right now:
<memory_fragments>
{memory_context}
</memory_fragments>

Task:
Cross-pollinate these fragments. Generate a novel, non-obvious idea, hypothesis, or project topic.
Think outside the box.

Output ONLY a JSON object wrapped in <seed> tags, with the following keys:
- "topic": A catchy title for the idea.
- "description": A 1-2 sentence explanation of the idea and how it connects the fragments.

Example:
<seed>
{{
  "topic": "Automated Market Maker for compute via x402",
  "description": "Connecting the memory of GPU shortages with the x402 micro-payment protocol to create a spot market."
}}
</seed>
"""

    log(f"☁️ Daydreaming... cross-pollinating {sample_size} memory fragments using {args.model}...")
    response = call_llm(args.api_base, args.api_key, args.model, prompt, args.api_type, args.temperature)
    if not response:
        log("❌ No response from LLM. Aborting.")
        raise SystemExit(1)

    # Case-insensitive tag matching and handle extra whitespace
    seed_match = re.search(r"<seed>\s*(.*?)\s*</seed>", response, re.DOTALL | re.IGNORECASE)
    if seed_match:
        try:
            seed_data = json.loads(seed_match.group(1).strip())
            seed_data["id"] = f"dd-{uuid.uuid4().hex[:8]}"
            seed_data["source"] = "skill-daydream"
            seed_data["maturity"] = 10  # Initial maturity for daydream seeds
            seed_data["created_at"] = datetime.datetime.now().isoformat()

            os.makedirs(os.path.dirname(seeds_file), exist_ok=True)
            with open(seeds_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(seed_data, ensure_ascii=False) + "\n")

            log(f"💡 Idea generated and planted in Topic Lab: {seed_data['topic']}")
        except json.JSONDecodeError as e:
            log(f"❌ Failed to parse LLM output as JSON: {e}")
            log(f"Raw LLM output snippet: {response[:500]}")
            raise SystemExit(1)
    else:
        log("❌ LLM output did not contain valid <seed> tags.")
        log(f"Raw LLM output snippet: {response[:500]}")
        raise SystemExit(1)

if __name__ == "__main__":
    main()

import os
import argparse
import datetime
import subprocess
import sys

# Inject runtime/scripts into sys.path to access logger_helper
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.append(os.path.join(repo_root, "runtime", "scripts"))
from logger_helper import setup_six6_logging
from runtime_io import append_jsonl, load_jsonl, write_jsonl

logger = None

def log(msg):
    if logger:
        logger.info(msg)
    else:
        print(msg)


def load_seeds(filepath):
    return [record.data for record in load_jsonl(filepath, allow_missing=True)]

def save_seeds(filepath, seeds):
    write_jsonl(filepath, seeds)

def emit_inbox_event(base_dir, payload):
    inbox_path = os.path.join(base_dir, "data", "inbox.jsonl")
    payload = dict(payload)
    payload.setdefault("type", "topic-lab-event")
    payload.setdefault("source", "skill-topic-lab")
    payload.setdefault("ts", int(datetime.datetime.now().timestamp()))
    append_jsonl(inbox_path, payload)

def plant_seed(seed):
    """Convert a mature seed into a GitHub Issue."""
    title = f"[topic-lab] {seed.get('topic', 'Untitled Seed')}"
    body = f"## 💡 Mature Idea from Topic Lab\n\n**Description:**\n{seed.get('description', '')}\n\n**Source:** {seed.get('source', 'unknown')}\n**Generated:** {seed.get('created_at', 'unknown')}"

    log(f"🌱 Planting seed '{title}' to GitHub Issue...")
    try:
        cmd = ["gh", "issue", "create", "--title", title, "--body", body, "--label", "idea"]
        if seed.get("repo"):
            cmd.extend(["--repo", seed["repo"]])
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        issue_url = result.stdout.strip()
        log("✅ Issue created successfully.")
        return True, issue_url
    except FileNotFoundError:
        log("⚠️ `gh` CLI not found. Skipping issue creation.")
        return False, ""
    except subprocess.CalledProcessError as e:
        stderr = e.stderr if isinstance(e.stderr, str) else e.stderr.decode("utf-8")
        log(f"❌ Failed to create issue. Error: {stderr}")
        return False, ""

def main():
    parser = argparse.ArgumentParser(description="Run daily maintenance on the Topic Lab (Farm).")
    parser.add_argument("--base-dir", default=".", help="Base directory of the agent.")
    parser.add_argument("--tick", action="store_true", help="Perform daily decay and maturity checks.")
    parser.add_argument("--add-water", type=str, help="Add +10 maturity to a specific seed ID.")
    args = parser.parse_args()

    # Initialize Logger
    global logger
    logger = setup_six6_logging("topic-lab", args.base_dir)

    seeds_file = os.path.join(args.base_dir, "data", "topic-lab-seeds.jsonl")
    seeds = load_seeds(seeds_file)

    if not seeds:
        log("🪹 Topic Lab is empty. No seeds to process.")
        return

    updated_seeds = []

    if args.add_water:
        for seed in seeds:
            if seed.get("id") == args.add_water and seed.get("status", "active") == "active":
                seed["maturity"] = min(100, seed.get("maturity", 0) + 10)
                seed["last_event"] = "watered"
                log(f"💧 Watered seed '{seed.get('topic')}'. Maturity is now {seed['maturity']}.")
                emit_inbox_event(args.base_dir, {
                    "event": "seed-watered",
                    "seed_id": seed.get("id"),
                    "topic": seed.get("topic"),
                    "status": seed.get("status", "active"),
                })
            updated_seeds.append(seed)
        save_seeds(seeds_file, updated_seeds)
        return

    if args.tick:
        log("⏱️ Running daily tick in Topic Lab...")
        for seed in seeds:
            status = seed.get("status", "active")
            if status != "active":
                updated_seeds.append(seed)
                continue

            maturity = seed.get("maturity", 10)

            # Check maturity thresholds
            if maturity >= 80:
                success, issue_url = plant_seed(seed)
                if success:
                    seed["status"] = "planted"
                    seed["planted_issue_url"] = issue_url
                    seed["last_event"] = "planted"
                    emit_inbox_event(args.base_dir, {
                        "event": "seed-planted",
                        "seed_id": seed.get("id"),
                        "topic": seed.get("topic"),
                        "status": "planted",
                        "msg": f"Seed planted into GitHub Issue: {seed.get('topic')}",
                    })
            else:
                # Apply decay
                seed["maturity"] = max(0, maturity - 5)
                if seed["maturity"] <= 20:
                    log(f"🍂 Seed '{seed.get('topic')}' withered (composted) due to low maturity.")
                    seed["status"] = "composted"
                    seed["last_event"] = "composted"
                    emit_inbox_event(args.base_dir, {
                        "event": "seed-composted",
                        "seed_id": seed.get("id"),
                        "topic": seed.get("topic"),
                        "status": "composted",
                        "msg": f"Seed composted after decay: {seed.get('topic')}",
                    })

            updated_seeds.append(seed)

        save_seeds(seeds_file, updated_seeds)
        log("✅ Topic Lab tick complete.")

if __name__ == "__main__":
    main()

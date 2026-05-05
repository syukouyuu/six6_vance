import os
import sys
import datetime
import argparse

# Inject runtime/scripts into sys.path to access logger_helper
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.append(os.path.join(repo_root, "runtime", "scripts"))
from logger_helper import setup_six6_logging

logger = None

def log(msg):
    if logger:
        logger.info(msg)
    else:
        print(msg)

def main():
    parser = argparse.ArgumentParser(description="Append a memory to today's journal.")
    parser.add_argument("text", help="The memory content to store.")
    parser.add_argument("--base-dir", default=".", help="Base directory containing the memory/ folder.")
    args = parser.parse_args()

    # Initialize Logger
    global logger
    logger = setup_six6_logging("memory", args.base_dir)

    today = datetime.datetime.now().strftime("%Y-%m-%d")
    mem_dir = os.path.join(args.base_dir, "memory")
    os.makedirs(mem_dir, exist_ok=True)
    file_path = os.path.join(mem_dir, f"{today}.md")

    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    entry = f"- **[{timestamp}]** {args.text}\n"

    with open(file_path, "a", encoding="utf-8") as f:
        f.write(entry)

    log(f"✅ Memory saved to {file_path}")

if __name__ == "__main__":
    main()

import os
import argparse
import datetime
import sys

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
    parser = argparse.ArgumentParser(description="Update the NOW.md short-term context.")
    parser.add_argument("text", help="The new context/task to write.")
    parser.add_argument("--base-dir", default=".", help="Base directory.")
    args = parser.parse_args()

    # Initialize Logger
    global logger
    logger = setup_six6_logging("memory", args.base_dir)

    file_path = os.path.join(args.base_dir, "NOW.md")
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    content = f"# NOW (Current Context)\n\n*Last updated: {timestamp}*\n\n{args.text}\n"
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    log(f"✅ NOW.md updated at {file_path}")

if __name__ == "__main__":
    main()

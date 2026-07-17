import os
import argparse
import subprocess
import datetime
import sys


sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "runtime", "scripts"))
from runtime_io import apply_env_defaults  # noqa: E402
from logger_helper import setup_six6_logging  # noqa: E402


logger = None


def log(msg):
    if logger:
        logger.info(msg)
    else:
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{ts}] {msg}", flush=True)


def modules_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run_module_script(agent_base_dir, module, script_name, extra_args=None):
    script_path = os.path.join(modules_root(), module, "scripts", script_name)
    if not os.path.exists(script_path):
        log(f"⚠️ Warning: Script {script_path} not found. Skipping.")
        return False

    cmd = [sys.executable, script_path, "--base-dir", os.path.abspath(agent_base_dir)]
    if extra_args:
        cmd.extend(extra_args)

    log(f"[pulse] 🫀 Triggering: {module}/{script_name}")
    
    try:
        # We no longer redirect to a file here because the module script
        # now handles its own daily rolling logging via logger_helper.
        subprocess.run(cmd, check=True)
        return True
    except subprocess.CalledProcessError as e:
        if e.returncode == 75:
            log(f"⚠️ {module} returned retryable meditation output failure; rerun the nightly pulse after reviewing its saved output.")
            return False
        log(f"❌ Error in {module}: process exited with error.")
        return False
    except Exception as e:
        log(f"❌ System error: {e}")
        return False

def main():
    apply_env_defaults()
    parser = argparse.ArgumentParser(description="The Heartbeat/Pulse of the Organic OS.")
    parser.add_argument("--base-dir", default=os.environ.get("SIX6_BASE_DIR"), help="Writable base directory for the agent state (or set SIX6_BASE_DIR).")
    parser.add_argument("pulse_type", choices=["heartbeat", "daily", "nightly", "idle"], help="Type of pulse to trigger.")
    args = parser.parse_args()
    if not args.base_dir:
        parser.error("--base-dir is required unless SIX6_BASE_DIR is set")

    pulse = args.pulse_type
    agent_base_dir = os.path.abspath(args.base_dir)

    global logger
    logger = setup_six6_logging("runtime", agent_base_dir)

    log(f"=== 💓 Initiating {pulse.upper()} pulse ===")

    if pulse == "heartbeat":
        # Frequent check (e.g., every 5-10 minutes)
        # 1. Process Inbox
        run_module_script(agent_base_dir, "skill-autoloop", "process_inbox.py")
        
    elif pulse == "daily":
        # Runs once a day (e.g., 10:00 AM)
        # 1. Farm/Topic Lab maintenance
        run_module_script(agent_base_dir, "skill-topic-lab", "farm.py", ["--tick"])
        
    elif pulse == "nightly":
        # Runs once at night (e.g., 02:00 AM)
        # 1. Meditate and consolidate memory
        run_module_script(agent_base_dir, "skill-meditation", "meditate.py")
        
    elif pulse == "idle":
        # Runs randomly when system load is low
        # 1. Daydream
        run_module_script(agent_base_dir, "skill-daydream", "daydream.py")

    log(f"=== 💓 {pulse.upper()} pulse complete ===")

if __name__ == "__main__":
    main()

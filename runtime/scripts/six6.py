import argparse
import datetime
import json
import os
import subprocess
import sys

# Inject current directory into sys.path to access logger_helper
sys.path.append(os.path.dirname(__file__))
from logger_helper import setup_six6_logging
from runtime_io import SchemaValidationError, load_jsonl, load_schema

MODULES = [
    "skill-memory",
    "skill-meditation",
    "skill-daydream",
    "skill-topic-lab",
    "skill-autoloop",
    "skill-monitor",
]

logger = None

def log(msg):
    if logger:
        logger.info(msg)
    else:
        print(msg)


def repo_root():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def env_file_path():
    return os.path.join(repo_root(), ".env")


def load_env_file(path):
    values = {}
    if not os.path.exists(path):
        return values
    with open(path, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if not key:
                continue
            if value and len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            values[key] = value
    return values


def apply_env_defaults(path):
    for key, value in load_env_file(path).items():
        os.environ.setdefault(key, value)


def default_base_dir():
    env_value = os.environ.get("SIX6_BASE_DIR")
    if env_value:
        return os.path.abspath(env_value)

    file_values = load_env_file(env_file_path())
    if file_values.get("SIX6_BASE_DIR"):
        return os.path.abspath(file_values["SIX6_BASE_DIR"])

    return repo_root()


def ensure_file(path, default_content=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(default_content)


def init_base_dir(base_dir):
    ensure_file(os.path.join(base_dir, "NOW.md"), "# NOW (Current Context)\n\n")
    ensure_file(os.path.join(base_dir, "MEMORY.md"), "# MEMORY\n\n")
    ensure_file(os.path.join(base_dir, "data", "inbox.jsonl"))
    ensure_file(os.path.join(base_dir, "data", "topic-lab-seeds.jsonl"))
    ensure_file(os.path.join(base_dir, "data", "evolution.md"))
    os.makedirs(os.path.join(base_dir, "memory"), exist_ok=True)
    os.makedirs(os.path.join(base_dir, "deadletter"), exist_ok=True)
    print(f"Initialized six6 base dir at {base_dir}")


def validate_base_dir(base_dir):
    inbox_path = os.path.join(base_dir, "data", "inbox.jsonl")
    seeds_path = os.path.join(base_dir, "data", "topic-lab-seeds.jsonl")
    issues = []

    for path, schema_name in ((inbox_path, "inbox-item"), (seeds_path, "topic-lab-seed")):
        try:
            load_jsonl(path, schema=load_schema(schema_name))
        except (SchemaValidationError, ValueError) as exc:
            issues.extend(str(exc).splitlines())

    if issues:
        print("Validation failed:")
        for issue in issues:
            print(f"- {issue}")
        return 1

    print("Validation passed.")
    return 0


def doctor(base_dir):
    checks = []
    checks.append(("base_dir_exists", os.path.isdir(base_dir)))
    checks.append(("memory_dir_exists", os.path.isdir(os.path.join(base_dir, "memory"))))
    checks.append(("data_dir_exists", os.path.isdir(os.path.join(base_dir, "data"))))
    checks.append(("gh_available", subprocess.run(["which", "gh"], capture_output=True).returncode == 0))

    status = "ok" if all(result for _, result in checks) else "warn"

    modules = {}
    six6_root = repo_root()
    for module in MODULES:
        modules[module] = os.path.isdir(os.path.join(six6_root, module))

    payload = {
        "updated_at": datetime.datetime.now().isoformat(),
        "status": status,
        "base_dir": base_dir,
        "checks": {name: result for name, result in checks},
        "modules": modules,
    }

    health_path = os.path.join(base_dir, "data", "health.json")
    os.makedirs(os.path.dirname(health_path), exist_ok=True)
    with open(health_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if status == "ok" else 1


def pulse(command_base_dir, pulse_type):
    script = os.path.join(repo_root(), "skill-monitor", "scripts", "pulse.py")
    cmd = [sys.executable, script, "--base-dir", command_base_dir, pulse_type]
    return subprocess.run(cmd).returncode


def main():
    apply_env_defaults(env_file_path())

    parser = argparse.ArgumentParser(description="six6 runtime entrypoint")
    subparsers = parser.add_subparsers(dest="command", required=True)
    default_dir = default_base_dir()

    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("--base-dir", default=default_dir)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--base-dir", default=default_dir)

    doctor_parser = subparsers.add_parser("doctor")
    doctor_parser.add_argument("--base-dir", default=default_dir)

    pulse_parser = subparsers.add_parser("pulse")
    pulse_parser.add_argument("pulse_type", choices=["heartbeat", "daily", "nightly", "idle"])
    pulse_parser.add_argument("--base-dir", default=default_dir)

    args = parser.parse_args()

    # Initialize Logger
    global logger
    logger = setup_six6_logging("runtime", args.base_dir)

    if args.command == "init":
        init_base_dir(os.path.abspath(args.base_dir))
        return
    if args.command == "validate":
        raise SystemExit(validate_base_dir(os.path.abspath(args.base_dir)))
    if args.command == "doctor":
        raise SystemExit(doctor(os.path.abspath(args.base_dir)))
    if args.command == "pulse":
        raise SystemExit(pulse(os.path.abspath(args.base_dir), args.pulse_type))


if __name__ == "__main__":
    main()

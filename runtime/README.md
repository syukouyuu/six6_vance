# six6 Runtime

This layer turns the protocol into something an OpenClaw user can actually run.

## Commands

```bash
python3 runtime/scripts/six6.py init --base-dir /path/to/agent
python3 runtime/scripts/six6.py validate --base-dir /path/to/agent
python3 runtime/scripts/six6.py doctor --base-dir /path/to/agent
python3 runtime/scripts/six6.py pulse heartbeat --base-dir /path/to/agent
```

## Responsibilities

- Bootstrap required directories and files.
- Validate protocol files.
- Expose a single runtime CLI.
- Emit `data/health.json` for schedulers and operators.
- Keep orchestration concerns outside the six cognitive modules.

## Shared IO Helpers

`runtime/scripts/runtime_io.py` is the common boundary for protocol file IO:

- `load_jsonl`, `write_jsonl`, and `append_jsonl` handle JSONL parsing and atomic replacement writes.
- `load_schema`, `validate_records`, and `validate_object` provide reusable line-level and field-level validation for local protocol schemas.
- `generate_candidate_id` and `generate_memory_id` centralize the protocol ID rules for candidate and future Memory node generation.

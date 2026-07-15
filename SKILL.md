# six6 — Agent Runtime Interface

This file tells an agent how to interact with six6 at runtime. For the full system
picture, see [ARCHITECTURE.md](ARCHITECTURE.md). For installing/deploying six6 itself,
see [distribution/SKILL.md](distribution/SKILL.md).

## When to Use This

- **Something worth remembering happened** (a decision, a fact, a preference, an
  outcome) → append it to today's daily memory file:
  ```bash
  python3 skill-memory/scripts/remember.py "what happened" --base-dir /path/to/agent/root
  ```
- **Your current context/task changed** (you're now working on something different,
  or need to leave a note for your next self) → overwrite the short-term context file:
  ```bash
  python3 skill-memory/scripts/update_now.py "what you're doing now" --base-dir /path/to/agent/root
  ```

Both scripts default `--base-dir` to `.`; always pass the real base dir explicitly.

## Read-Only Files

`MEMORY.md` and `data/evolution.md` are outputs of the nightly `skill-meditation`
reflection process. Read them for context. Never write to them directly — meditation
owns them.

## Not the Agent's Job

Do not trigger meditation, advance topic-lab seed lifecycles, or run the memory
review/approval/ingestion pipeline yourself. Those are owned by cron-driven pulses
and a human reviewer. Your job is limited to `remember.py` and `update_now.py`.

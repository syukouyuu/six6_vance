<div align="center">

# 🧬 six6

**6-Module Organic AI Agent Ecosystem built with absolute file-system decoupling.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![OpenClaw Skill](https://img.shields.io/badge/OpenClaw-Skill-blue.svg)](https://github.com/openclaw/openclaw)
[![CI](https://github.com/syukouyuu/six6_vance/actions/workflows/ci.yml/badge.svg)](https://github.com/syukouyuu/six6_vance/actions/workflows/ci.yml)
[![GitHub stars](https://img.shields.io/github/stars/syukouyuu/six6_vance?style=social)](https://github.com/syukouyuu/six6_vance)

*Modular · State via File System · Works everywhere*

[Architecture](#-architecture) · [Modules](#-the-6-modules) · [Quick Start](#-quick-start)

</div>

---

## 😤 Problem

```
You: "I want an AI Agent that can think, remember, and generate ideas."
Current frameworks: "Here is a massive 1GB monolithic orchestrator with tight Python couplings."
```

six6 decomposes the core cognitive functions of an AI Agent into **6 independent modules**. They do not import each other. They do not share memory space. They communicate entirely through a standardized set of files (Markdown & JSONL).

**What six6 actually is.** This is a memory & cognition framework for agents, not a self-contained skill that works the moment it's installed. Running it means initializing a writable base directory, wiring one or more modules into cron (or systemd), and — for the memory pipeline in particular — committing to a standing human review step before anything gets written into FalkorDB. It is a small persistent system that happens to live in a skill directory, not a drop-in trick. In exchange, an agent gets durable, reviewable long-term memory and a slow background thought process instead of a context window that resets.

The repository also includes three supporting layers that sit underneath the six modules:

- `protocol/`: file contracts and schemas.
- `runtime/`: init, validate, doctor, and pulse entrypoints.
- `distribution/`: packaging guidance for install and migration.

The six modules are independently enable-able: install just `skill-memory` for basic short/long-term memory, or run the entire suite for a living, breathing organic AI entity with reflection, idle-time ideation, and a task loop.

## 🧬 Architecture

Absolute decoupling is our core principle:
- **No Python imports between modules.**
- **Standardized data flow** via Markdown (for cognition/memory) and JSONL (for queues/seeds).

Read the detailed [ARCHITECTURE.md](ARCHITECTURE.md) for data flow specifications.

## 🧱 The 6 Modules

1. **`skill-memory` (Cerebral Cortex)**
   - Manages short-term context (`NOW.md`) and long-term daily episodic memory (`memory/YYYY-MM-DD.md`).
   - Maintains the core cognitive summary (`MEMORY.md`).

2. **`skill-meditation` (Reflection)**
   - Deep reflection mechanism. Runs nightly to synthesize the day's memory into the core `MEMORY.md`.

3. **`skill-daydream` (Divergent Ideation)**
   - Randomly samples historical memory fragments during idle time to generate serendipitous ideas, outputting them as JSON objects to the Topic Lab.

4. **`skill-topic-lab` (Greenhouse / Farm)**
   - Manages the lifecycle of generated ideas (seeds).
   - Tracks maturity. When a seed hits >80% maturity, it automatically triggers external outputs (e.g., creating a GitHub Issue).

5. **`skill-autoloop` (Action Center)**
   - The task queuing and execution hub.
   - Manages `inbox.jsonl` and handles escalation protocols (e.g., `needs-decision`).

6. **`skill-monitor` (Life Support / Heartbeat)**
   - The chronometer and health checker. Manages system pulses and triggers for the other modules.

## 🚀 Quick Start

1. Clone the repository into your skills directory:
   ```bash
   git clone https://github.com/syukouyuu/six6_vance.git
   ```
2. Check the `ARCHITECTURE.md` file to understand the required file structures.
3. Hook any or all modules into your agent's cron or trigger system.
   For overnight `nightly` runs, schedule them after midnight if you prefer; the meditation step processes yesterday's memory by default.
4. Bootstrap a writable base directory:
   ```bash
   python3 runtime/scripts/six6.py init --base-dir /path/to/agent/root
   ```
   Or set a default writable base directory in `.env`:
   ```bash
   SIX6_BASE_DIR=/path/to/agent/root
   ```
   After that, `init`, `validate`, `doctor`, and `pulse` will use that path by default unless `--base-dir` is passed explicitly.
5. Validate protocol files:
   ```bash
   python3 runtime/scripts/six6.py validate --base-dir /path/to/agent/root
   ```
6. Try the included sample base directory:
   ```bash
   python3 runtime/scripts/six6.py validate --base-dir demo
   python3 runtime/scripts/six6.py pulse heartbeat --base-dir demo
   ```

`demo/` is sample state only. Keep live agent state in a separate writable base
directory; the repository root intentionally does not track `MEMORY.md`,
`NOW.md`, `data/`, or `log/`.

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.

## Development

Minimum supported Python: **3.11** (matches Debian bookworm's default `python3`, which is what the production container ships). Avoid syntax that requires newer versions, e.g. backslashes inside f-string expressions (PEP 701, Python 3.12+).

Run tests in an isolated environment:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest
```

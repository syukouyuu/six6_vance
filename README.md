<div align="center">

# 🧬 six6

**6-Module Organic AI Agent Ecosystem built with absolute file-system decoupling.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![OpenClaw Skill](https://img.shields.io/badge/OpenClaw-Skill-blue.svg)](https://github.com/openclaw/openclaw)
[![CI](https://github.com/syukouyuu/six6_vance/actions/workflows/ci.yml/badge.svg)](https://github.com/syukouyuu/six6_vance/actions/workflows/ci.yml)
[![GitHub stars](https://img.shields.io/github/stars/syukouyuu/six6_vance?style=social)](https://github.com/syukouyuu/six6_vance)

*Modular · State via File System · Works everywhere*

[Architecture](#-architecture) · [Modules](#-the-6-modules) · [Quick Start](#-quick-start)

[中文版 (Chinese Version)](README_zh.md)

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

## 🔧 Dependencies & Environment

### Python Dependencies

- `requirements.txt`: Production dependencies. Currently only includes `falkordb>=1,<2` (FalkorDB's Python client SDK, used in `skill-memory` to connect to the graph database).
- `requirements-dev.txt`: Development/testing dependencies. Currently only includes `pytest>=8,<10`.

Installation (both files need to be installed, otherwise a `ModuleNotFoundError` will occur when hitting code paths dependent on `falkordb`):

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt
```

Note: The `falkordb` Python package is merely a client library. It **is not** the FalkorDB service itself. Installing this package does not mean a usable graph database is present in your local/CI environment. See the next section.

### FalkorDB Service (Real Graph Database, Not Optional)

Memory ingestion/querying in `skill-memory` (e.g., `skill-memory/scripts/memory_ingestion_executor.py`) depends on a genuinely running FalkorDB instance (a graph database based on the Redis protocol). **This is not an optional component that can be mocked out in production.**

Production containers (like the `Dockerfile` in the root of `openclaw`) already have `redis-tools` and the `falkordb` Python package installed, but **do not include the FalkorDB service itself**. The service needs to be started as a separate container from the one running the six6 code.

Start a FalkorDB container for local development/testing:

```bash
docker run -d --name falkordb-memory -p 6379:6379 \
  -e REDIS_ARGS="--requirepass <your_password>" \
  falkordb/falkordb:latest
```

The production environment uses the `requirepass` authentication mode, meaning FalkorDB requires a password to connect. When running integration tests or manually verifying locally, it is best to replicate the same authentication configuration instead of conveniently running an instance without a password, otherwise you won't be able to catch NOAUTH-related issues (see the "Known Issues" section below).

Environment variables used for connection (corresponding to the argparse definitions in `skill-memory/scripts/memory_ingestion_executor.py`):

| Environment Variable | Default Value | Description |
| --- | --- | --- |
| `FALKORDB_HOST` | `localhost` | FalkorDB host address |
| `FALKORDB_PORT` | `6379` | FalkorDB port |
| `FALKORDB_USER` | None | FalkorDB ACL username, not needed for most deployments |
| `FALKORDB_PASS` | None | FalkorDB password, corresponding to the password set in `REDIS_ARGS="--requirepass <your_password>"` in the `docker run` command above |
| `SIX6_FALKOR_GRAPH` | `FreyaGraph` | The graph name used in production |

Example:

```bash
export FALKORDB_HOST=localhost
export FALKORDB_PORT=6379
export FALKORDB_PASS=your-local-password
python3 skill-memory/scripts/memory_ingestion_executor.py --base-dir demo
```

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.

## 🛠️ Development

Minimum supported Python: **3.11** (matches Debian bookworm's default `python3`, which is what the production container ships). Avoid syntax that requires newer versions, e.g. backslashes inside f-string expressions (PEP 701, Python 3.12+).

Run tests in an isolated environment:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m pytest
```

### Unit Tests (Default, No Real FalkorDB Required)

`python -m pytest` (or just `pytest`) runs all test cases **without** the `integration` marker, verifying logic entirely by mocking FalkorDB. No local services are required. The CI (`.github/workflows/ci.yml`) currently also only runs this scope: `pip install -r requirements.txt -r requirements-dev.txt` then `python -m pytest`, **excluding integration tests with a real FalkorDB**.

`pytest.ini` has `addopts = -m "not integration"` set, so the default execution automatically skips integration tests. No extra arguments or CI configuration changes are needed.

### Integration Tests (Requires Real FalkorDB, Skipped by Default)

`tests/test_memory_ingestion_integration.py` is an integration test that connects directly to a real FalkorDB (no mocking). It is marked with `pytest.mark.integration` and covers 5 scenarios:

1. Round-trip of multi-line content (content written and then read back is identical)
2. Querying a non-existent `candidate_id` and confirming it returns `None`
3. Unset optional fields read back as `None` instead of empty strings
4. Fidelity of `maturity` (int type), ensuring it is not serialized into a string, etc.
5. Consecutive `ingest` of the same data twice does not produce duplicate nodes

To run manually:

```bash
pytest -m integration
```

Requires a real FalkorDB to be running (see the "FalkorDB Service" section above), and connection parameters are similarly passed via `FALKORDB_HOST` / `FALKORDB_PORT` / `FALKORDB_USER` / `FALKORDB_PASS`. When unable to connect (`RedisError` / `ConnectionError` / `OSError` / `RuntimeError`, including NOAUTH), it will elegantly skip via `pytest.skip` instead of throwing an error and blowing up—so it's safe to run `pytest -m integration` even when there's no FalkorDB locally, it just won't be able to test actual communication layer issues.

The integration tests use an independent test graph `six6IntegrationTestGraph` (can be overridden with the `SIX6_TEST_FALKOR_GRAPH` environment variable) and won't touch the production `FreyaGraph`. Every `candidate_id` in the tests has a random uuid suffix to avoid conflicts, and self-created nodes are automatically deleted during teardown.

**Why normal unit tests can't catch real communication layer bugs**: The unit tests mock the actual network/protocol interaction between `FalkorGraphBackend` and FalkorDB (Redis protocol response parsing, authentication handshakes), only verifying "given a certain return value, whether the upper-level logic processing is correct", naturally assuming the underlying communication is reliable and authenticated successfully. The real parsing misalignments or authentication state misjudgments happen exactly in this mocked layer, so "unit tests all green" does not equal "communication with real FalkorDB is fine". You must rely on integration tests or manual verification against a real container.

## 🐛 Known Issues / Pitfall Records

The following two issues were **only discovered during manual verification against a real FalkorDB container environment**, and were not caught by normal unit tests (which mock FalkorDB):

1. **FalkorDB communication parsing misalignment leading to duplicate nodes**: There was a misalignment in the text/field parsing logic for FalkorDB return results, causing the same record to be written repeatedly into the graph database, generating duplicate nodes. In the unit tests, because the return values were manually constructed mock data, it couldn't cover edge cases in the real response format, so this issue was not exposed.
2. **NOAUTH falsely judged as successful**: When connecting to FalkorDB, if authentication fails (NOAUTH), the error handling logic did not correctly identify this failure state, leading subsequent processes to mistakenly believe the connection/write had already succeeded. Similarly, the authentication handshake is skipped under mock scenarios, so this type of issue cannot be tested.

**A reminder to future contributors**: When modifying code related to `skill-memory/scripts/memory_ingestion_executor.py` or `FalkorGraphBackend`, do not just merge it because the unit tests are all green. Please do at least one of the following:

- Start a local FalkorDB container (see commands above) and manually run the related scripts once to verify real behavior;
- Run `pytest -m integration` once to confirm the 5 scenarios in `tests/test_memory_ingestion_integration.py` still pass.

All green unit tests only prove the business logic itself hasn't degraded; they cannot prove that there are no issues with the communication layer against a real FalkorDB.

# 🧠 skill-memory (Cerebral Cortex)

This module handles the foundational memory structures for the Agent. It does not use vector databases; instead, it relies on structured Markdown files to ensure 100% human readability and file-system absolute decoupling.

## Standard File Structures

- `memory/YYYY-MM-DD.md`: The daily episodic memory. Append-only log of events, decisions, and observations.
- `NOW.md`: Short-term working memory. Overwritten frequently during state changes or session handovers.
- `MEMORY.md`: Long-term consolidated cognitive summary (updated by `skill-meditation`).

## Scripts

候选生成默认会将命中协议“严禁入库”规则的条目自动写入
`memory/deprecated_decisions/`，并从人工待审清单移除。需要完全退回人工审核时，
在运行环境或 `.env` 中设置：

```bash
MEMORY_RULE_AUTO_DEPRECATE=false
```

自动弃只会废弃，不会自动核准；废弃记录带有 `decided_by: rule` 供抽查。

### 1. Append to Daily Memory
```bash
python3 scripts/remember.py "Found a new way to optimize the Topic Lab using standard JSON." --base-dir /path/to/agent/root
```
This will automatically create or append to `memory/2026-04-03.md` with a timestamp.

### 2. Update Short-Term Context
```bash
python3 scripts/update_now.py "Currently researching HTTP 402 protocols for x402 integration. Blocked by missing API key." --base-dir /path/to/agent/root
```
This overwrites `NOW.md` so that the next agent session knows exactly what was happening.

### 3. Ingest Approved Decisions
Requires `redis-cli` on PATH in the environment that runs this script (install
via `apt-get install redis-tools` or equivalent). It is invoked directly as a
subprocess, so make sure it's installed wherever this script actually runs.

```bash
python3 scripts/memory_ingestion_executor.py --base-dir /path/to/agent/root --graph FreyaGraph
```
This reads only `memory/approved_decisions/latest-approved-seeds.jsonl`, validates
`approved-decision.v2`, looks up existing FalkorDB `(:Memory)` nodes by
`candidate_id`, then creates or updates `memory-node.v2` nodes. Each run writes an
auditable JSONL report under `memory/ingestion/`.

### 4. Audit Existing FalkorDB Memory Nodes
Before cutting over a historical graph, export current `(:Memory)` node
properties to JSONL and run:

```bash
python3 scripts/memory_graph_maintenance.py \
  --export-jsonl memory/graph-audit/memory-export.jsonl \
  --report-json memory/graph-audit/memory-audit-report.json \
  --plan-jsonl memory/graph-audit/memory-migration-plan.jsonl \
  --rollback-jsonl memory/graph-audit/memory-rollback.jsonl
```

This is intentionally separate from ingestion. It inventories existing fields,
flags duplicates and dirty historical nodes, and prepares cleanup and rollback
artifacts. See `docs/FALKORDB_MEMORY_CLEANUP_MIGRATION.md`.

### 5. Rebuild Historical Meditation Outputs
Use this when rebuilding `MEMORY.md` and `data/evolution.md` from raw daily
memory files after an environment migration:

```bash
python3 scripts/backfill_memory.py \
  --base-dir /path/to/agent/root \
  --from 2026-04-01 \
  --to 2026-05-22 \
  --api-key "$LLM_API_KEY" \
  --model gpt-4o
```

The script runs in rebuild mode by default: it clears `MEMORY.md` and
`data/evolution.md`, then replays existing `memory/YYYY-MM-DD.md` files in
date order. Missing dates are logged and skipped explicitly. Use `--append` only
when you intentionally want to preserve existing outputs before replaying.

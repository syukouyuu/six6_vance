# 🧠 skill-memory (Cerebral Cortex)

This module handles the foundational memory structures for the Agent. It does not use vector databases; instead, it relies on structured Markdown files to ensure 100% human readability and file-system absolute decoupling.

## Standard File Structures

- `memory/YYYY-MM-DD.md`: The daily episodic memory. Append-only log of events, decisions, and observations.
- `NOW.md`: Short-term working memory. Overwritten frequently during state changes or session handovers.
- `MEMORY.md`: Long-term consolidated cognitive summary (updated by `skill-meditation`).

## Scripts

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
```bash
python3 scripts/memory-ingestion-executor.py --base-dir /path/to/agent/root --graph FreyaGraph
```
This reads only `memory/approved_decisions/latest-approved-seeds.jsonl`, validates
`approved-decision.v2`, looks up existing FalkorDB `(:Memory)` nodes by
`candidate_id`, then creates or updates `memory-node.v2` nodes. Each run writes an
auditable JSONL report under `memory/ingestion/`.

### 4. Audit Existing FalkorDB Memory Nodes
Before cutting over a historical graph, export current `(:Memory)` node
properties to JSONL and run:

```bash
python3 scripts/memory-graph-maintenance.py \
  --export-jsonl memory/graph-audit/memory-export.jsonl \
  --report-json memory/graph-audit/memory-audit-report.json \
  --plan-jsonl memory/graph-audit/memory-migration-plan.jsonl \
  --rollback-jsonl memory/graph-audit/memory-rollback.jsonl
```

This is intentionally separate from ingestion. It inventories existing fields,
flags duplicates and dirty historical nodes, and prepares cleanup and rollback
artifacts. See `docs/FALKORDB_MEMORY_CLEANUP_MIGRATION.md`.

# six6 Architecture

This document records the actual local operating model currently used with six6.
It is intended as a working architecture note for this workspace, not as a public product spec.

## Core Separation

The system now has two clearly different output lanes:

1. `daydream / topic-lab`
   - Purpose: generate speculative ideas and incubate them.
   - Primary file: `data/topic-lab-seeds.jsonl`

2. `nightly memory distillation`
   - Purpose: compress daily memory into durable memory candidates for human review.
   - Primary files:
     - `MEMORY.md`
     - `data/evolution.md`
     - `memory/candidates/*.jsonl` in the outer workspace

These two lanes must not be mixed.

## Module Roles

### 1. skill-memory
- Role: short-term and daily memory storage.
- Files:
  - `NOW.md`: current context
  - `memory/YYYY-MM-DD.md`: daily memory input
  - `MEMORY.md`: distilled long-term summary

### 2. skill-meditation
- Role: nightly reflection and compression.
- Input:
  - `memory/YYYY-MM-DD.md`
- Output:
  - rewrites `MEMORY.md`
  - appends `data/evolution.md`
- Current operating rule:
  - nightly runs at overnight times such as `02:40`
  - default target date is the previous day, not the current day

### 3. skill-daydream
- Role: speculative ideation.
- Input:
  - memory context sampled from `memory/`
- Output:
  - appends structured idea seeds to `data/topic-lab-seeds.jsonl`

### 4. skill-topic-lab
- Role: manages idea-seed lifecycle.
- Input:
  - `data/topic-lab-seeds.jsonl`
- Output:
  - updates seed maturity and status
  - emits lifecycle events to `data/inbox.jsonl`

### 5. skill-autoloop
- Role: consumes inbox tasks and closes loops.
- Input:
  - `data/inbox.jsonl`
- Output:
  - action results and escalations

### 6. skill-monitor
- Role: scheduling and health operations.
- Output:
  - cron-triggered execution
  - health state in `data/health.json`

## Runtime and Review Pipeline

### A. Daily memory lane
1. External memory is synchronized into `six6_lab/memory/YYYY-MM-DD.md`.
2. `pulse nightly` runs meditation against the previous day.
3. six6 updates:
   - `six6_lab/MEMORY.md`
   - `six6_lab/data/evolution.md`
4. `memory-candidate-generator` converts those outputs into:
   - `memory/candidates/YYYY-MM-DD-memory-candidates.jsonl`
   - `memory/candidates/latest-memory-candidates.jsonl`
5. `memory-review-report` reads the candidates JSONL and produces a human-readable review report.
   - Report format must show both:
     - `review_id`, a short batch-local display ordinal for mobile reading
     - the real `candidate_id` from the JSONL record
   - Display ordinals such as `01`, `02`, `03` are serialized for auditability but must never replace the real candidate identifier.
6. Master performs manual review.
7. `memory-decision-router` splits reviewed records into:
   - `memory/approved_decisions/*.jsonl`
   - `memory/deprecated_decisions/*.jsonl`
8. `memory_ingestion_executor` reads only:
   - `memory/approved_decisions/latest-approved-seeds.jsonl`
9. Approved records are written into FalkorDB.

### B. Daydream lane
1. `pulse idle` or related triggers run `skill-daydream`.
2. New idea seeds are appended to `data/topic-lab-seeds.jsonl`.
3. `pulse daily` or `skill-topic-lab` advances maturity and lifecycle state.
4. `pulse heartbeat` consumes resulting inbox events.

## File Ownership Rules

### Files owned by six6
- `NOW.md`
- `memory/YYYY-MM-DD.md`
- `MEMORY.md`
- `data/evolution.md`
- `data/topic-lab-seeds.jsonl`
- `data/inbox.jsonl`
- `data/health.json`

### Files owned by the outer memory workflow
- `memory/candidates/*.jsonl`
- `memory/approved_decisions/*.jsonl`
- `memory/deprecated_decisions/*.jsonl`
- `memory/deprecated_decisions.md`

## Operational Rules

1. `topic-lab-seeds.jsonl` is a creative seed pool, not a direct memory-ingestion source.
2. `MEMORY.md` and `data/evolution.md` are human-readable distillation outputs, not final database input by themselves.
3. Structured memory ingestion candidates must come from `memory/candidates/*.jsonl`.
4. FalkorDB ingestion must read only approved records.
5. Human review is mandatory before FalkorDB ingestion.
6. Field-level definitions for `topic`, `content`, `candidate_id`, `deprecation_reason`, and final `Memory.id` are governed by `docs/MEMORY_V1_PROTOCOL.md`.

## Logging Strategy

The system uses a standardized "Plan A" logging strategy designed for VPS stability and easy maintenance.

### 1. Daily Logs
Each module (meditation, daydream, etc.) manages its own logs via `runtime/scripts/logger_helper.py`.
- **Path**: `base_dir/log/YYYY-MM-DD_module.log`
- **Maintenance**: No automatic cleanup; logs are kept indefinitely. Requires manual management or external logrotate configurations for VPS environments.
- **Format**: Standardized `[timestamp] [level] [name] message`.

### 2. Autonomous Logging
Scripts are designed to be "log-autonomous."
- They do not rely on shell redirection (`>>`) for primary logging.
- Logger output is written to the daily file and mirrored to stdout with full date/time prefixes.
- Raw stderr is also mirrored into the daily file as `ERROR`, while still being printed to the original stderr stream.
- Uncaught Python exceptions are written to the daily file with traceback details.
- They preserve emojis (✅, ❌, 🧘) for quick visual debugging.

### 3. VPS Integration
- **Crontab**: Can run scripts directly without shell redirection for primary Python logs; long-term cleanup is handled manually or by external logrotate.
- **Monitoring**: `StreamHandler` and stderr tee remain active, allowing real-time monitoring via `tail -f` or existing terminal-based observers.

## Protocol Authority

`ARCHITECTURE.md` defines workflow, file boundaries, and ownership.

`docs/MEMORY_V1_PROTOCOL.md` is the authoritative source for:

- field meanings
- required fields
- length limits
- approved/deprecated JSONL structure
- candidate ID handling
- final FalkorDB memory update rules

When generating or updating memory workflow files, do not infer field semantics from `ARCHITECTURE.md` alone.
For any field-level decision, follow `docs/MEMORY_V1_PROTOCOL.md`.

## ID Rules

There are two different ID layers in this workflow:

1. Candidate ID
   - Used in `memory/candidates/*.jsonl`
   - Used for human review, approval, and deprecation routing
   - Only needs to be unique and stable within the candidate workflow

2. Final database ID
   - Used when writing `Memory` records into FalkorDB
   - Must follow the database-side memory ID convention
   - Must not depend on a report-only temporary label

Operationally:

- review reports may show machine-stable candidate IDs such as `mem-260425-a1b2c3d4e5f6` or `evo-260425-a1b2c3d4e5f6`
- review reports may also show `review_id` values such as `01` or `02`, but those are not valid routing identifiers
- approved records should preserve that source value as `candidate_id`
- the ingestion layer should generate or assign the final FalkorDB memory ID separately

## Cron Notes

The currently validated real-world chain is:

- `02:30` memory sync into `six6_lab/memory/`
- `02:40` `pulse nightly`

If cron changes are made close to trigger time, restart `crond` and verify execution with logs.

## Validation Notes

- `runtime/scripts/six6.py validate` checks six6 protocol files.
- This validation does not replace memory review.
- A valid six6 run can still produce candidates that should be discarded by human judgment.

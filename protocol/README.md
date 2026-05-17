# six6 Core Protocol

This layer defines the stable contracts shared by all six6 modules.
It exists to preserve the six-module design while making the system portable,
testable, and safe to integrate into different OpenClaw deployments.

## Goals

- Preserve the six-module architecture.
- Make file contracts machine-checkable.
- Keep module coupling at the file-protocol level.

## Canonical Files

- `NOW.md`: short-term working state.
- `MEMORY.md`: long-term consolidated memory.
- `memory/YYYY-MM-DD.md`: append-only daily memory log.
- `data/inbox.jsonl`: central task and event queue.
- `data/topic-lab-seeds.jsonl`: idea seed database.
- `memory/candidates/YYYY-MM-DD-memory-candidates.jsonl`: distilled memory candidates awaiting review.
- `memory/candidates/latest-memory-candidates.jsonl`: latest candidate batch pointer/copy.
- `data/health.json`: runtime health heartbeat.
- `data/evolution.md`: meditation evolution log.

## Schemas

- `schemas/inbox-item.schema.json`
- `schemas/topic-lab-seed.schema.json`
- `schemas/memory-candidate.schema.json`
- `schemas/health.schema.json`

## Memory Candidate Contract

`memory-candidate.schema.json` defines one JSONL record emitted by
`memory-candidate-generator`. Its stable key is `candidate_id`, which is used
for review reports, approval routing, discard routing, and ingestion idempotency.
The final FalkorDB `Memory.id` remains an ingestion-layer database key and must
not directly reuse `candidate_id`.

Generate `candidate_id` deterministically as:

```text
<prefix>-<YYMMDD>-<sha256(source_file + "\n" + source_section + "\n" + topic + "\n" + content)[0:12]>
```

Recommended prefixes map to `category`: `fac`, `pro`, `les`, `rel`, `evo`.
Use `mem` only for legacy or general candidates.

Example JSONL:

- `examples/memory-candidates/valid-sample.jsonl`

## Closed Loop

The canonical six6 loop is:

1. `skill-daydream` writes seeds into `topic-lab-seeds.jsonl`.
2. `skill-topic-lab` matures, composts, or plants those seeds.
3. `skill-topic-lab` emits lifecycle events into `inbox.jsonl`.
4. `skill-autoloop` dispatches inbox items and can water a seed by writing back into Topic Lab.

This preserves the original six-module mental model while formalizing the interfaces.

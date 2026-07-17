# FalkorDB Memory Cleanup and Migration Strategy

This plan protects the new `approved-decision.v2` -> `memory-node.v2`
ingestion chain from historical FalkorDB data that was written with older or
unstable fields.

## Artifact Boundaries

Keep the three jobs separate:

- **Inventory script**: exports existing `(:Memory)` node properties from the
  graph into JSONL. The export is a read-only snapshot and is the rollback
  source of truth.
- **Maintenance script**: `skill-memory/scripts/memory_graph_maintenance.py`
  reads that export and writes an audit report, a migration action plan, and a
  rollback JSONL file. It does not write to FalkorDB directly.
- **Audit report**: JSON summary of node counts, field inventory, schema
  violations, duplicate groups, and per-node migration actions.

The ingestion executor remains separate. It only reads
`memory/approved_decisions/latest-approved-seeds.jsonl` and writes
`memory-node.v2` nodes by `candidate_id`.

## Snapshot and Audit

Create an export where each line is one `(:Memory)` node properties object:

```bash
python3 skill-memory/scripts/memory_graph_maintenance.py \
  --export-jsonl memory/graph-audit/memory-export.jsonl \
  --report-json memory/graph-audit/memory-audit-report.json \
  --plan-jsonl memory/graph-audit/memory-migration-plan.jsonl \
  --rollback-jsonl memory/graph-audit/memory-rollback.jsonl
```

The script reports:

- all fields currently present on `(:Memory)` nodes
- missing required `memory-node.v2` fields
- unknown historical fields
- duplicate `candidate_id` groups
- duplicate normalized `topic + content` fingerprints
- nodes that must be quarantined instead of auto-cleaned

## Duplicate Strategy

Duplicate detection is ordered:

1. **Same `candidate_id`**: hard duplicate. `candidate_id` is the ingestion
   idempotency key, so more than one `(:Memory)` node with the same value must
   be manually merged or quarantined before new ingestion runs.
2. **Same normalized `topic + content` fingerprint**: soft duplicate. These
   require human review because old nodes may lack `candidate_id` or may be
   different memories with similar wording.
3. **Same `id`**: graph identity conflict. Treat as a database integrity issue;
   do not continue migration until resolved.

When choosing a canonical node in a duplicate group, prefer the node that:

- has a valid `candidate_id`
- has `schema_version == "memory-node.v2"`
- has an `id` matching `memnode-<YYMMDD>-<hash16>`
- has the newest valid `approved_at` or `ingested_at`
- contains no unknown fields

Non-canonical duplicates should be quarantined or deleted only after the export
and rollback file have been preserved.

## Field Retention Rules

Retain only the Memory Node V2 contract fields:

- `id`
- `candidate_id`
- `topic`
- `content`
- `timestamp`
- `category`
- `maturity`
- `source`
- `source_file`
- `source_section`
- `approved_at`
- `ingested_at`
- `schema_version`

Drop historical or lane-crossing fields from `(:Memory)` nodes, including:

- candidate review display fields such as `review_id`
- candidate generation internals such as `hash_input` and `created_at`
- deprecated decision fields such as `deprecation_reason` and `deprecated_at`
- topic-lab/daydream fields such as `seed_id`, `status`, `last_event`
- operational scratch fields that are not in `memory-node-v2.schema.json`

If a historical field contains important context, move it back to the source
document or candidate/decision audit log. Do not keep it on final `(:Memory)`.

## Migration Rules

Automatic cleanup is allowed only for low-risk property normalization:

- strip fields outside `memory-node-v2.schema.json`
- normalize missing or legacy `schema_version` to `memory-node.v2` when all
  required fields are otherwise valid

Manual review or quarantine is required when:

- `candidate_id` is missing
- `Memory.id` reuses `candidate_id`
- `candidate_id` appears on multiple nodes
- required V2 fields are missing
- a field violates the V2 schema
- content fingerprint duplicates another node

Quarantined nodes must stay out of the new ingestion boundary until a human
creates or approves a valid `approved-decision.v2` record for them.

## Rollback

Before applying any migration action:

1. Save the raw export JSONL.
2. Save `memory-rollback.jsonl`.
3. Record the graph name, export time, and command used to produce the export.

Rollback restores each changed node by its `id` when present, then by
`candidate_id`, and finally by export index for nodes that lack both. If a
manual delete is performed, recreate the node from the matching rollback
`restore` object.

## Cutover Gate

Do not run the new ingestion executor against a graph until:

- the audit report shows zero duplicate `candidate_id` groups
- all existing `(:Memory)` nodes either validate as `memory-node.v2` or are
  explicitly quarantined
- historical lane fields have been removed from active `(:Memory)` nodes
- the latest migration plan and rollback file are archived next to the export

After cutover, new writes must come only from
`skill-memory/scripts/memory_ingestion_executor.py`.

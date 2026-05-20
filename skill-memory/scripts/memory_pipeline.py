import argparse
import datetime
import os
import re
import sys


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.append(os.path.join(REPO_ROOT, "runtime", "scripts"))

from runtime_io import (  # noqa: E402
    JsonlRecord,
    candidate_hash_input,
    generate_candidate_id,
    load_jsonl,
    load_schema,
    validate_records,
    write_jsonl,
)


DEFAULT_SOURCES = ("MEMORY.md", "data/evolution.md")
DECISION_APPROVE = {"approve", "approved", "keep", "入库", "核准", "通过"}
DECISION_DEPRECATE = {"deprecate", "deprecated", "discard", "reject", "废弃", "丢弃", "拒绝"}


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def today_from_timestamp(timestamp):
    return timestamp[:10]


def generate_candidates(base_dir, *, source_files=DEFAULT_SOURCES, created_at=None):
    created_at = created_at or utc_now()
    candidates = []
    seen = set()

    for source_file in source_files:
        path = os.path.join(base_dir, source_file)
        if not os.path.exists(path):
            continue
        candidates.extend(_extract_candidates(path, source_file, created_at=created_at, seen=seen))

    candidates.sort(key=lambda item: (item["source_file"], item["source_section"], item["topic"], item["content"]))
    for index, candidate in enumerate(candidates, start=1):
        candidate["review_id"] = f"{index:02d}"

    schema = load_schema("memory-candidate.v1", REPO_ROOT)
    validate_records(_records_for_validation(candidates, "generated candidates"), schema)
    return candidates


def write_candidate_batch(base_dir, candidates, *, created_at):
    date = today_from_timestamp(created_at)
    directory = os.path.join(base_dir, "memory", "candidates")
    batch_path = os.path.join(directory, f"{date}-memory-candidates.jsonl")
    latest_path = os.path.join(directory, "latest-memory-candidates.jsonl")
    write_jsonl(batch_path, candidates)
    write_jsonl(latest_path, candidates)
    return batch_path, latest_path


def render_review_report(candidates):
    lines = ["# 提炼产物抽查报告", ""]
    for candidate in candidates:
        lines.extend(
            [
                f"## {candidate['review_id']} | {candidate['candidate_id']}",
                f"- topic: {candidate['topic']}",
                f"- category: {candidate['category']}",
                f"- source: {candidate['source_file']} / {candidate['source_section']}",
                f"- content: {candidate['content']}",
                "- decision: pending",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def write_review_report(base_dir, candidates, *, created_at):
    date = today_from_timestamp(created_at)
    directory = os.path.join(base_dir, "memory", "review")
    path = os.path.join(directory, f"{date}-memory-review.md")
    latest_path = os.path.join(directory, "latest-memory-review.md")
    content = render_review_report(candidates)
    from runtime_io import atomic_write_text  # imported lazily to keep the public imports small

    atomic_write_text(path, content)
    atomic_write_text(latest_path, content)
    return path, latest_path


def route_decisions(base_dir, candidates_path, review_path, *, decided_at=None):
    decided_at = decided_at or utc_now()
    candidates = [record.data for record in load_jsonl(candidates_path, schema=load_schema("memory-candidate.v1", REPO_ROOT), allow_missing=False)]
    candidate_by_id = {candidate["candidate_id"]: candidate for candidate in candidates}
    review_records = [record.data for record in load_jsonl(review_path, allow_missing=False)]

    approved = []
    deprecated = []
    for review in review_records:
        candidate_id = review.get("candidate_id")
        if candidate_id not in candidate_by_id:
            raise ValueError(f"unknown candidate_id in review decision: {candidate_id!r}")
        decision = _normalize_decision(review.get("decision", ""))
        candidate = candidate_by_id[candidate_id]
        if decision == "approved":
            approved.append(_approved_decision(candidate, decided_at))
        elif decision == "deprecated":
            reason = str(review.get("deprecation_reason") or review.get("reason") or "人工裁决废弃")
            deprecated.append(_deprecated_decision(candidate, reason, decided_at))
        else:
            raise ValueError(f"unsupported decision for {candidate_id}: {review.get('decision')!r}")

    validate_records(_records_for_validation(approved, "approved decisions"), load_schema("approved-decision.v2", REPO_ROOT))
    validate_records(_records_for_validation(deprecated, "deprecated decisions"), load_schema("deprecated-decision.v2", REPO_ROOT))
    return approved, deprecated


def write_decision_batches(base_dir, approved, deprecated, *, decided_at):
    date = today_from_timestamp(decided_at)
    approved_dir = os.path.join(base_dir, "memory", "approved_decisions")
    deprecated_dir = os.path.join(base_dir, "memory", "deprecated_decisions")
    approved_path = os.path.join(approved_dir, f"{date}-approved-seeds.jsonl")
    approved_latest = os.path.join(approved_dir, "latest-approved-seeds.jsonl")
    deprecated_path = os.path.join(deprecated_dir, f"{date}-deprecated-seeds.jsonl")
    deprecated_latest = os.path.join(deprecated_dir, "latest-deprecated-seeds.jsonl")
    write_jsonl(approved_path, approved)
    write_jsonl(approved_latest, approved)
    write_jsonl(deprecated_path, deprecated)
    write_jsonl(deprecated_latest, deprecated)
    return approved_path, approved_latest, deprecated_path, deprecated_latest


def _extract_candidates(path, source_file, *, created_at, seen):
    section = "root"
    candidates = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            raw = line.strip()
            if not raw:
                continue
            heading = re.match(r"^(#{1,6})\s+(.+)$", raw)
            if heading:
                section = _clean_text(heading.group(2), limit=80)
                continue
            item = re.match(r"^[-*]\s+(?:\*\*([^*]+)\*\*:?\s*)?(.+)$", raw)
            if not item:
                continue
            topic = _clean_text(item.group(1) or _topic_from_content(item.group(2)), limit=60)
            content = _clean_text(item.group(2), limit=200)
            if not topic or not content:
                continue
            category = _category_for(source_file, section, topic, content)
            timestamp = _timestamp_for(source_file, created_at)
            hash_input = candidate_hash_input(source_file, section, topic, content)
            candidate_id = generate_candidate_id(category, source_file, section, topic, content, timestamp=timestamp)
            if candidate_id in seen:
                continue
            seen.add(candidate_id)
            candidates.append(
                {
                    "review_id": "00",
                    "candidate_id": candidate_id,
                    "topic": topic,
                    "content": content,
                    "timestamp": timestamp,
                    "category": category,
                    "maturity": 1,
                    "source": source_file,
                    "source_file": source_file,
                    "source_section": section,
                    "created_at": created_at,
                    "schema_version": "memory-candidate.v1",
                    "hash_input": hash_input,
                }
            )
    return candidates


def _approved_decision(candidate, approved_at):
    decision = {
        key: candidate[key]
        for key in ("candidate_id", "topic", "content", "timestamp", "category", "maturity", "source", "source_file", "source_section")
    }
    decision["approved_at"] = approved_at
    decision["schema_version"] = "approved-decision.v2"
    return decision


def _deprecated_decision(candidate, reason, deprecated_at):
    return {
        "candidate_id": candidate["candidate_id"],
        "topic": candidate["topic"],
        "deprecation_reason": _clean_text(reason, limit=240),
        "source_file": candidate["source_file"],
        "deprecated_at": deprecated_at,
        "schema_version": "deprecated-decision.v2",
    }


def _records_for_validation(items, path):
    return [JsonlRecord(path=path, line_no=index, data=item) for index, item in enumerate(items, start=1)]


def _normalize_decision(value):
    decision = str(value).strip().lower()
    if decision in DECISION_APPROVE:
        return "approved"
    if decision in DECISION_DEPRECATE:
        return "deprecated"
    return decision


def _category_for(source_file, section, topic, content):
    text = f"{source_file} {section} {topic} {content}".lower()
    if "evolution" in source_file.lower() or "演进" in text or "进化" in text:
        return "evolution"
    if "protocol" in text or "协议" in text or "必须" in text:
        return "protocol"
    if "lesson" in text or "教训" in text or "风险" in text:
        return "lesson"
    if "关系" in text or "协作" in text or "consensus" in text:
        return "relation"
    return "fact"


def _timestamp_for(source_file, fallback):
    match = re.search(r"(20\d{2})[-/](\d{2})[-/](\d{2})", source_file)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}T00:00:00Z"
    return fallback


def _topic_from_content(content):
    content = re.sub(r"^[\[`*_#>\s-]+", "", content)
    return re.split(r"[。.!?；;：:]", content, maxsplit=1)[0]


def _clean_text(value, *, limit):
    text = re.sub(r"\s+", " ", str(value)).strip()
    text = re.sub(r"^\[?([0-9: -]+)\]?\s*", "", text)
    return text[:limit].rstrip()


def add_common_args(parser):
    parser.add_argument("--base-dir", default=".", help="Base directory containing MEMORY.md and data/.")
    parser.add_argument("--created-at", help="UTC generation timestamp, useful for reproducible tests.")


def candidate_generator_main():
    parser = argparse.ArgumentParser(description="Generate memory-candidate.v1 JSONL from MEMORY.md and data/evolution.md.")
    add_common_args(parser)
    parser.add_argument("--source", action="append", dest="sources", help="Source file relative to base-dir; may be repeated.")
    args = parser.parse_args()
    created_at = args.created_at or utc_now()
    candidates = generate_candidates(args.base_dir, source_files=tuple(args.sources or DEFAULT_SOURCES), created_at=created_at)
    paths = write_candidate_batch(args.base_dir, candidates, created_at=created_at)
    print(f"generated {len(candidates)} candidates")
    for path in paths:
        print(path)


def review_report_main():
    parser = argparse.ArgumentParser(description="Render a human review report from memory-candidate.v1 JSONL.")
    add_common_args(parser)
    parser.add_argument("--candidates", help="Candidate JSONL path. Defaults to latest-memory-candidates.jsonl.")
    args = parser.parse_args()
    created_at = args.created_at or utc_now()
    candidates_path = args.candidates or os.path.join(args.base_dir, "memory", "candidates", "latest-memory-candidates.jsonl")
    candidates = [record.data for record in load_jsonl(candidates_path, schema=load_schema("memory-candidate.v1", REPO_ROOT), allow_missing=False)]
    paths = write_review_report(args.base_dir, candidates, created_at=created_at)
    print(f"wrote review report for {len(candidates)} candidates")
    for path in paths:
        print(path)


def decision_router_main():
    parser = argparse.ArgumentParser(description="Route reviewed memory decisions into approved/deprecated JSONL.")
    add_common_args(parser)
    parser.add_argument("--candidates", help="Candidate JSONL path. Defaults to latest-memory-candidates.jsonl.")
    parser.add_argument("--review", required=True, help="Reviewed JSONL with candidate_id, decision, and optional deprecation_reason.")
    args = parser.parse_args()
    decided_at = args.created_at or utc_now()
    candidates_path = args.candidates or os.path.join(args.base_dir, "memory", "candidates", "latest-memory-candidates.jsonl")
    approved, deprecated = route_decisions(args.base_dir, candidates_path, args.review, decided_at=decided_at)
    paths = write_decision_batches(args.base_dir, approved, deprecated, decided_at=decided_at)
    print(f"approved {len(approved)} candidates; deprecated {len(deprecated)} candidates")
    for path in paths:
        print(path)

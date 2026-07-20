"""Read-only query CLI over FalkorDB Memory nodes.

Gives the runtime agent a way to search long-term graph memory without any
embedding provider. Strictly read-only: only MATCH/RETURN queries are issued.
"""

import argparse
import json
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from memory_ingestion_executor import FalkorGraphBackend  # noqa: E402


QUERY_FIELDS = ("topic", "content", "category", "maturity", "timestamp", "candidate_id", "ingested_at")


class ReadOnlyMemoryBackend(FalkorGraphBackend):
    def search(self, *, keyword=None, category=None, maturity=None, order_by="timestamp", limit=10):
        conditions = []
        params = {"limit": int(limit)}
        if keyword:
            conditions.append("(toLower(m.topic) CONTAINS toLower($keyword) OR toLower(m.content) CONTAINS toLower($keyword))")
            params["keyword"] = keyword
        if category:
            conditions.append("m.category = $category")
            params["category"] = category
        if maturity:
            conditions.append("m.maturity = $maturity")
            params["maturity"] = maturity
        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        returned = ", ".join(f"m.{key}" for key in QUERY_FIELDS)
        result = self._query(
            f"MATCH (m:Memory){where} RETURN {returned} ORDER BY m.{order_by} DESC LIMIT $limit",
            params,
        )
        return [{key: value for key, value in zip(QUERY_FIELDS, row)} for row in result.result_set]


def format_markdown(memories):
    if not memories:
        return "(no matching memories)"
    lines = []
    for memory in memories:
        lines.append(f"### {memory.get('topic') or '(untitled)'}")
        lines.append(f"- category: {memory.get('category')} | maturity: {memory.get('maturity')} | timestamp: {memory.get('timestamp')}")
        lines.append(f"- candidate_id: {memory.get('candidate_id')}")
        lines.append("")
        lines.append(str(memory.get("content") or ""))
        lines.append("")
    return "\n".join(lines).rstrip()


def memory_query_main():
    parser = argparse.ArgumentParser(description="Read-only search over FalkorDB Memory nodes.")
    parser.add_argument("--keyword", help="Case-insensitive substring match on topic or content.")
    parser.add_argument("--category", help="Exact match on category.")
    parser.add_argument("--maturity", help="Exact match on maturity.")
    parser.add_argument("--recent", type=int, help="Return the N most recently ingested memories (orders by ingested_at).")
    parser.add_argument("--limit", type=int, default=10, help="Maximum results (default 10).")
    parser.add_argument("--format", choices=("md", "json"), default="md", help="Output format (default md).")
    parser.add_argument("--redis-host", default=os.environ.get("FALKORDB_HOST", "localhost"), help="FalkorDB host. Defaults to $FALKORDB_HOST.")
    parser.add_argument("--redis-port", type=int, default=int(os.environ.get("FALKORDB_PORT", "6379")), help="FalkorDB port. Defaults to $FALKORDB_PORT.")
    parser.add_argument("--redis-user", default=os.environ.get("FALKORDB_USER"), help="FalkorDB ACL username. Defaults to $FALKORDB_USER.")
    parser.add_argument("--redis-password", default=os.environ.get("FALKORDB_PASS"), help="FalkorDB password. Defaults to $FALKORDB_PASS.")
    args = parser.parse_args()

    graph_name = os.environ.get("SIX6_FALKOR_GRAPH")
    if not graph_name:
        parser.error("environment variable SIX6_FALKOR_GRAPH must be set to the target graph name")

    order_by = "timestamp"
    limit = args.limit
    if args.recent is not None:
        order_by = "ingested_at"
        limit = args.recent

    backend = ReadOnlyMemoryBackend(
        graph=graph_name,
        host=args.redis_host,
        port=args.redis_port,
        username=args.redis_user,
        password=args.redis_password,
    )
    memories = backend.search(
        keyword=args.keyword,
        category=args.category,
        maturity=args.maturity,
        order_by=order_by,
        limit=limit,
    )
    if args.format == "json":
        print(json.dumps(memories, ensure_ascii=False, indent=2))
    else:
        print(format_markdown(memories))


if __name__ == "__main__":
    memory_query_main()

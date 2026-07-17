"""Integration tests for FalkorGraphBackend against a real FalkorDB instance.

Unlike tests/test_memory_ingestion_executor.py (which mocks FalkorDB entirely
or uses an in-memory FakeMemoryBackend), these tests exercise the real
redis-cli wire protocol / FalkorDB result-set parsing layer. They exist
because two production bugs (mis-parsed multi-line content causing duplicate
nodes, and a NOAUTH failure being silently treated as success) both slipped
past the mocked unit tests.

These tests are marked `integration` and are excluded from the default
`pytest` run (see pytest.ini: `addopts = -m "not integration"`). Run them
explicitly with:

    pytest -m integration tests/test_memory_ingestion_integration.py

They require a real, reachable FalkorDB instance. Connection info is read
from the same environment variables the executor itself uses:
FALKORDB_HOST, FALKORDB_PORT, FALKORDB_USER, FALKORDB_PASS. If no instance
is reachable, tests are skipped (not failed) so environments without a
FalkorDB container are unaffected.
"""
import os
import sys
import tempfile
import uuid

import pytest
from redis.exceptions import RedisError

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(os.path.join(ROOT, "runtime", "scripts"))
sys.path.append(os.path.join(ROOT, "skill-memory", "scripts"))

from runtime_io import write_jsonl  # noqa: E402
from memory_ingestion_executor import (  # noqa: E402
    FalkorGraphBackend,
    ingest_approved_decisions,
)

pytestmark = pytest.mark.integration

TEST_GRAPH = os.environ.get("SIX6_TEST_FALKOR_GRAPH", "six6IntegrationTestGraph")


def _connect_or_skip():
    try:
        backend = FalkorGraphBackend(
            graph=TEST_GRAPH,
            host=os.environ.get("FALKORDB_HOST", "localhost"),
            port=int(os.environ.get("FALKORDB_PORT", "6379")),
            username=os.environ.get("FALKORDB_USER"),
            password=os.environ.get("FALKORDB_PASS"),
        )
        # Force an actual round-trip so auth/connection errors surface now,
        # not on first use inside a test.
        backend.find_by_candidate_id("__six6_integration_connectivity_probe__")
    except (RedisError, ConnectionError, OSError, RuntimeError) as exc:
        pytest.skip(f"no reachable FalkorDB instance for integration tests: {exc}")
    return backend


@pytest.fixture
def backend():
    return _connect_or_skip()


@pytest.fixture
def candidate_id():
    """A unique candidate_id per test so runs never collide, plus teardown
    that deletes any Memory node it created. Must match
    approved-decision.v2's candidate_id pattern: pro-YYMMDD-[a-f0-9]{12}.
    """
    cid = f"pro-260520-{uuid.uuid4().hex[:12]}"
    yield cid
    cleanup_backend = _connect_or_skip()
    cleanup_backend._query(
        "MATCH (m:Memory {candidate_id: $candidate_id}) DELETE m",
        {"candidate_id": cid},
    )


def _approved_record(candidate_id, **overrides):
    record = {
        "candidate_id": candidate_id,
        "topic": "Memory ingestion integration test",
        "content": "line one\nline two\nline three",
        "timestamp": "2026-05-20T13:00:00Z",
        "category": "protocol",
        "maturity": 1,
        "source": "tests/test_memory_ingestion_integration.py",
        "source_file": "tests/test_memory_ingestion_integration.py",
        "source_section": "integration test",
        "approved_at": "2026-05-20T13:30:00Z",
        "schema_version": "approved-decision.v2",
    }
    record.update(overrides)
    return record


class TestFalkorGraphBackendIntegration:
    def test_multiline_content_round_trips_without_corruption(self, backend, candidate_id):
        content = "第一行内容\n第二行内容，带有更多文字\n第三行，结尾。"
        backend.create_memory(
            {
                "id": f"memnode-{uuid.uuid4().hex[:16]}",
                "candidate_id": candidate_id,
                "topic": "multiline test",
                "content": content,
                "timestamp": "2026-05-20T13:00:00Z",
                "category": "protocol",
                "maturity": 1,
                "source": "test",
                "schema_version": "memory-node.v2",
                "ingested_at": "2026-05-20T14:00:00Z",
            }
        )

        found = backend.find_by_candidate_id(candidate_id)

        assert found is not None
        assert found["content"] == content

    def test_missing_candidate_id_returns_none(self, backend):
        missing_id = f"pro-integ-does-not-exist-{uuid.uuid4().hex[:16]}"

        assert backend.find_by_candidate_id(missing_id) is None

    def test_unset_optional_field_reads_back_as_python_none(self, backend, candidate_id):
        backend.create_memory(
            {
                "id": f"memnode-{uuid.uuid4().hex[:16]}",
                "candidate_id": candidate_id,
                "topic": "optional field test",
                "content": "content without source_file",
                "timestamp": "2026-05-20T13:00:00Z",
                "category": "protocol",
                "maturity": 1,
                "source": "test",
                "schema_version": "memory-node.v2",
                "ingested_at": "2026-05-20T14:00:00Z",
                # source_file intentionally omitted
            }
        )

        found = backend.find_by_candidate_id(candidate_id)

        assert found is not None
        assert found["source_file"] is None
        assert found["source_file"] != ""

    def test_maturity_field_reads_back_as_python_int(self, backend, candidate_id):
        backend.create_memory(
            {
                "id": f"memnode-{uuid.uuid4().hex[:16]}",
                "candidate_id": candidate_id,
                "topic": "maturity type test",
                "content": "content",
                "timestamp": "2026-05-20T13:00:00Z",
                "category": "protocol",
                "maturity": 1,
                "source": "test",
                "schema_version": "memory-node.v2",
                "ingested_at": "2026-05-20T14:00:00Z",
            }
        )

        found = backend.find_by_candidate_id(candidate_id)

        assert found is not None
        assert found["maturity"] == 1
        assert isinstance(found["maturity"], int)
        assert not isinstance(found["maturity"], bool)
        assert found["maturity"] != "1"

    def test_repeated_ingest_approved_decisions_does_not_duplicate_node(self, backend, candidate_id):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = os.path.join(tmpdir, "approved.jsonl")
            approved = _approved_record(candidate_id)
            write_jsonl(input_path, [approved])

            first = ingest_approved_decisions(input_path, backend, ingested_at="2026-05-20T14:00:00Z")
            second = ingest_approved_decisions(input_path, backend, ingested_at="2026-05-20T14:00:00Z")

            assert first["summary"] == {"created": 1, "updated": 0, "skipped": 0, "failed": 0}
            assert second["summary"] == {"created": 0, "updated": 0, "skipped": 1, "failed": 0}

            result = backend._query(
                "MATCH (m:Memory {candidate_id: $candidate_id}) RETURN count(m)",
                {"candidate_id": candidate_id},
            )
            assert result.result_set[0][0] == 1

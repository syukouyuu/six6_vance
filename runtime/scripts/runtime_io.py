import datetime
import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass


CATEGORY_PREFIXES = {
    "fact": "fac",
    "protocol": "pro",
    "lesson": "les",
    "relation": "rel",
    "evolution": "evo",
}

SCHEMA_FILES = {
    "inbox-item": "inbox-item.schema.json",
    "topic-lab-seed": "topic-lab-seed.schema.json",
    "memory-candidate.v1": "memory-candidate.schema.json",
    "approved-decision.v2": "approved-decision-v2.schema.json",
    "deprecated-decision.v2": "deprecated-decision-v2.schema.json",
    "memory-node.v2": "memory-node-v2.schema.json",
}


@dataclass(frozen=True)
class JsonlRecord:
    path: str
    line_no: int
    data: dict


class JsonlError(ValueError):
    def __init__(self, path, line_no, message):
        super().__init__(f"{path}:{line_no}: {message}")
        self.path = path
        self.line_no = line_no
        self.message = message


class SchemaValidationError(ValueError):
    def __init__(self, errors):
        super().__init__("\n".join(errors))
        self.errors = errors


def repo_root():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def env_file_path(root=None):
    return os.path.join(root or repo_root(), ".env")


def load_env_file(path):
    values = {}
    if not os.path.exists(path):
        return values
    with open(path, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if not key:
                continue
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            values[key] = value
    return values


def apply_env_defaults(path=None):
    """Load missing environment variables and return keys supplied by the file."""
    applied = set()
    for key, value in load_env_file(path or env_file_path()).items():
        if key not in os.environ:
            os.environ[key] = value
            applied.add(key)
    return applied


def schema_path(schema_name, root=None):
    filename = SCHEMA_FILES.get(schema_name, schema_name)
    return os.path.join(root or repo_root(), "protocol", "schemas", filename)


def load_schema(schema_name, root=None):
    with open(schema_path(schema_name, root), "r", encoding="utf-8") as handle:
        return json.load(handle)


def iter_jsonl(path, *, allow_missing=True, skip_blank=True):
    if not os.path.exists(path):
        if allow_missing:
            return
        raise FileNotFoundError(path)

    with open(path, "r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            raw = line.strip()
            if not raw and skip_blank:
                continue
            try:
                value = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise JsonlError(path, line_no, f"invalid JSON: {exc.msg}") from exc
            if not isinstance(value, dict):
                raise JsonlError(path, line_no, "expected JSON object")
            yield JsonlRecord(path=path, line_no=line_no, data=value)


def load_jsonl(path, *, schema=None, allow_missing=True):
    records = list(iter_jsonl(path, allow_missing=allow_missing))
    if schema is not None:
        validate_records(records, schema)
    return records


def write_jsonl(path, items):
    lines = [json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n" for item in items]
    atomic_write_text(path, "".join(lines))


def append_jsonl(path, item):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")


def atomic_write_text(path, content):
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=f".{os.path.basename(path)}.", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def validate_records(records, schema):
    errors = []
    for record in records:
        errors.extend(validate_object(record.data, schema, location=f"{record.path}:{record.line_no}"))
    if errors:
        raise SchemaValidationError(errors)


def validate_object(value, schema, *, location="record"):
    errors = []
    expected_type = schema.get("type")
    if expected_type and not _matches_type(value, expected_type):
        return [f"{location}: expected {expected_type}"]

    if expected_type == "object":
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                errors.append(f"{location}.{key}: missing required field")

        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in properties:
                    errors.append(f"{location}.{key}: unexpected field")

        for key, property_schema in properties.items():
            if key in value:
                errors.extend(_validate_field(value[key], property_schema, f"{location}.{key}"))
    return errors


def _validate_field(value, schema, location):
    errors = []
    expected_type = schema.get("type")
    if expected_type and not _matches_type(value, expected_type):
        return [f"{location}: expected {expected_type}"]

    if "const" in schema and value != schema["const"]:
        errors.append(f"{location}: expected {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{location}: expected one of {schema['enum']}")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{location}: shorter than minLength {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(f"{location}: longer than maxLength {schema['maxLength']}")
        if "pattern" in schema and not re.fullmatch(schema["pattern"], value):
            errors.append(f"{location}: does not match pattern {schema['pattern']}")
        if schema.get("format") == "date-time" and not _is_datetime(value):
            errors.append(f"{location}: expected date-time")
    if isinstance(value, int) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{location}: below minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{location}: above maximum {schema['maximum']}")
    return errors


def _matches_type(value, expected_type):
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "null":
        return value is None
    return True


def _is_datetime(value):
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        datetime.datetime.fromisoformat(normalized)
    except ValueError:
        return False
    return True


def candidate_hash_input(source_file, source_section, topic, content):
    return "\n".join([source_file, source_section, topic, content])


def generate_candidate_id(category, source_file, source_section, topic, content, *, timestamp):
    prefix = CATEGORY_PREFIXES.get(category, "mem")
    yymmdd = _yymmdd(timestamp)
    hash_input = candidate_hash_input(source_file, source_section, topic, content)
    digest = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{yymmdd}-{digest}"


def generate_memory_id(candidate_id, *, timestamp):
    yymmdd = _yymmdd(timestamp)
    digest = hashlib.sha256(f"memory-node.v2\n{candidate_id}".encode("utf-8")).hexdigest()[:16]
    return f"memnode-{yymmdd}-{digest}"


def _yymmdd(timestamp):
    if isinstance(timestamp, datetime.datetime):
        return timestamp.strftime("%y%m%d")
    text = str(timestamp)
    if len(text) >= 10 and re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", text):
        return f"{text[2:4]}{text[5:7]}{text[8:10]}"
    raise ValueError(f"timestamp must start with YYYY-MM-DD: {timestamp!r}")

#!/usr/bin/env python3
"""
Validates agent quality gate output against the JSON schema.
Returns exit code 0 on pass, 1 on fail — usable as a CI gate.

Usage:
    python scripts/validate_quality_gate.py path/to/agent-output.json
    # or pipe from stdin:
    cat agent-output.json | python scripts/validate_quality_gate.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    from jsonschema import Draft7Validator
except ImportError:
    print(
        "ERROR: jsonschema is not installed. Install it with: pip install jsonschema",
        file=sys.stderr,
    )
    sys.exit(1)


SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "quality-gate-output.schema.json"

MAX_INPUT_BYTES = 1_048_576  # 1 MB


BUSINESS_RULES: list[dict] = [
    {
        "name": "blocked_verdict_requires_reason",
        "check": lambda d: d["verdict"] != "blocked" or bool(d.get("block_reason", "").strip()),
        "message": "Verdict is 'blocked' but block_reason is empty.",
    },
    {
        "name": "no_empty_security_risks",
        "check": lambda d: all(len(r.strip()) > 5 for r in d["security_review"]["risks"]),
        "message": "Security risks contain empty or trivially short entries.",
    },
    {
        "name": "canonical_names_present",
        "check": lambda d: bool(d["refined_plan"].get("canonical_names")),
        "message": "Refined plan is missing canonical_names mapping.",
    },
    {
        "name": "acceptance_criteria_all_testable",
        "check": lambda d: all(ac.get("testable") is True for ac in d["acceptance_criteria"]),
        "message": "All acceptance criteria must have testable: true.",
    },
    {
        "name": "minimum_acceptance_criteria",
        "check": lambda d: len(d["acceptance_criteria"]) >= 3,
        "message": "Need at least 3 acceptance criteria for a production plan.",
    },
    {
        "name": "source_reference_has_real_id",
        "check": lambda d: len(d["source_reference"]["id"].strip()) > 0
        and d["source_reference"]["id"] != "TBD",
        "message": "source_reference.id is empty or 'TBD'. Must link to a real issue.",
    },
    {
        "name": "definition_of_done_not_generic",
        "check": lambda d: not any(
            "all tests pass" == item.lower().strip() for item in d["definition_of_done"]
        ),
        "message": "Definition of done contains generic entries. Be specific.",
    },
    {
        "name": "improvements_has_candidates",
        "check": lambda d: bool(
            d.get("improvements", {}).get("docs_to_update")
            or d.get("improvements", {}).get("proposed_ci_checks")
            or d.get("improvements", {}).get("agents_md_additions")
        ),
        "message": "Every quality gate review should produce at least one improvement candidate.",
    },
]


def validate_output(data: dict) -> list[str]:
    """Validate against JSON schema + business rules. Returns list of errors."""
    errors: list[str] = []

    if not SCHEMA_PATH.exists():
        errors.append(f"SCHEMA: Schema file not found at {SCHEMA_PATH}")
        return errors

    schema = json.loads(SCHEMA_PATH.read_text())
    validator = Draft7Validator(schema)
    for error in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path)):
        path = ".".join(str(p) for p in error.absolute_path) or "(root)"
        errors.append(f"SCHEMA: {path} — {error.message}")

    if not errors:
        for rule in BUSINESS_RULES:
            try:
                if not rule["check"](data):
                    errors.append(f"RULE [{rule['name']}]: {rule['message']}")
            except (KeyError, TypeError, IndexError) as e:
                errors.append(f"RULE [{rule['name']}]: Check failed with {e}")

    return errors


def main() -> None:
    if len(sys.argv) > 1:
        file_path = Path(sys.argv[1])
        if not file_path.exists():
            print(f"ERROR: File not found: {file_path}", file=sys.stderr)
            sys.exit(1)
        raw_bytes = file_path.read_bytes()
    else:
        raw_bytes = sys.stdin.buffer.read()

    if not raw_bytes.strip():
        print("ERROR: Empty input", file=sys.stderr)
        sys.exit(1)

    if len(raw_bytes) > MAX_INPUT_BYTES:
        print(
            f"GATE FAILED: Input exceeds {MAX_INPUT_BYTES // 1024}KB size limit",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        raw = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as e:
        print(f"GATE FAILED: Input is not valid UTF-8 — {e}", file=sys.stderr)
        sys.exit(1)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"GATE FAILED: Invalid JSON — {e}", file=sys.stderr)
        sys.exit(1)

    errors = validate_output(data)

    if errors:
        print(f"QUALITY GATE FAILED — {len(errors)} violation(s):\n", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"QUALITY GATE PASSED — verdict: {data['verdict']}")
        if data["verdict"] == "needs_refinement":
            print(f"   Needs refinement — {len(data['gaps_found'])} gaps identified.")
        sys.exit(0)


if __name__ == "__main__":
    main()

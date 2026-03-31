#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from autonomous_pipeline.memory.agent_memory import AgentMemoryClient
from autonomous_pipeline.memory.validation import validate_agent_memory


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate agent-memory integration for the autonomous pipeline")
    parser.add_argument("--project-path", default=".", help="Project path to scope validation")
    parser.add_argument("--memory-url", default="http://127.0.0.1:3377", help="agent-memory base URL")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    client = AgentMemoryClient(base_url=args.memory_url)
    report = validate_agent_memory(client, project_path=Path(args.project_path).resolve())
    print(json.dumps(report.to_dict(), indent=2))
    return 0 if report.overall_status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

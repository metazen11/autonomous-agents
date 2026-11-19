#!/usr/bin/env python3
"""Print bytes and estimated tokens of each rendered host file and agent-description block.

Tokens are estimated as ceil(bytes / 4) (no tokenizer dependency); compare runs, not absolutes.
"""
from __future__ import annotations

import argparse
import math
import re
from pathlib import Path

from autonomous_pipeline.host_sync import HOST_NAMES, HostTarget, host_agent_sources, render_host_instructions

DESCRIPTION_RE = re.compile(r"(?m)^description:\s*(.+)$")


def est_tokens(n_bytes: int) -> int:
    return math.ceil(n_bytes / 4)


def agent_descriptions(repo_root: Path, host: str) -> list[tuple[str, str]]:
    out = []
    for source in host_agent_sources(repo_root, host):
        match = DESCRIPTION_RE.search(source.read_text())
        if match:
            out.append((source.stem, match.group(1).strip()))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--host", action="append", choices=HOST_NAMES, help="default: claude, codex, anvil")
    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()
    print(f"{'host':8} {'instr_B':>8} {'~tok':>6} {'agents':>6} {'desc_B':>7} {'~tok':>6} {'max_desc':>8}")
    for host in args.host or ("claude", "codex", "anvil"):
        base = Path("/opt/anvil") if host == "anvil" else Path.home() / f".{host}"
        target = HostTarget(name=host, skill_path=base / "skills/autonomous/skill.md", agents_dir=base / "agents")
        size = len(render_host_instructions(repo_root, target).encode())
        descs = agent_descriptions(repo_root, host)
        desc_bytes = sum(len(f"- {name}: {desc}\n".encode()) for name, desc in descs)
        longest = max((len(desc) for _, desc in descs), default=0)
        print(f"{host:8} {size:8} {est_tokens(size):6} {len(descs):6} {desc_bytes:7} {est_tokens(desc_bytes):6} {longest:8}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

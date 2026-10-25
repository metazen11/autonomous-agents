from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence


HOST_NAMES = ("claude", "codex", "gemini", "cursor", "openclaw", "anvil")
DEFAULT_REPO_URL = "https://github.com/metazen11/autonomous-agents.git"
DEFAULT_INSTALL_DIR = Path("~/_CODING/autonomous_agents_mds").expanduser()


@dataclass(frozen=True, slots=True)
class HostSpec:
    name: str
    instruction_filename: str
    capability_tags: tuple[str, ...]
    config_format: str | None = None


HOST_SPECS = {
    "claude": HostSpec(
        name="claude",
        instruction_filename="CLAUDE.md",
        capability_tags=("instructions", "hooks", "plans", "todo", "memory", "plugins"),
        config_format="json",
    ),
    "codex": HostSpec(
        name="codex",
        instruction_filename="AGENTS.md",
        capability_tags=("instructions", "skills", "mcp", "plans", "todo", "memory", "subagents"),
        config_format="toml",
    ),
    "gemini": HostSpec(
        name="gemini",
        instruction_filename="GEMINI.md",
        capability_tags=("instructions", "mcp", "todo", "browser"),
        config_format="json",
    ),
    "cursor": HostSpec(
        name="cursor",
        instruction_filename="AGENTS.md",
        capability_tags=("instructions", "mcp", "todo"),
    ),
    "openclaw": HostSpec(
        name="openclaw",
        instruction_filename="AGENTS.md",
        capability_tags=("instructions", "todo", "local-runtime"),
    ),
    "anvil": HostSpec(
        name="anvil",
        instruction_filename="AGENTS.md",
        capability_tags=("instructions", "mcp", "todo", "memory", "skills", "tools", "local-runtime"),
        config_format="json",
    ),
}


@dataclass(slots=True)
class HostTarget:
    name: str
    skill_path: Path | None = None
    agents_dir: Path | None = None
    instructions_path: Path | None = None
    config_snippet_path: Path | None = None
    schemas_dir: Path | None = None
    scripts_dir: Path | None = None

    @property
    def configured(self) -> bool:
        return any(
            value is not None
            for value in (
                self.skill_path, self.agents_dir, self.instructions_path,
                self.config_snippet_path, self.schemas_dir, self.scripts_dir,
            )
        )


@dataclass(slots=True)
class SyncStatus:
    host: str
    configured: bool
    skill_in_sync: bool | None = None
    instructions_in_sync: bool | None = None
    config_snippet_in_sync: bool | None = None
    missing_agents: list[str] | None = None
    missing_schemas: list[str] | None = None
    missing_scripts: list[str] | None = None
    bench: list[str] | None = None
    bench_problems: list[str] | None = None


@dataclass(frozen=True, slots=True)
class AgentFile:
    name: str
    path: Path
    sha256: str
    mtime_ns: int


@dataclass(frozen=True, slots=True)
class AgentInventoryReport:
    repo_count: int
    target_count: int
    missing_from_repo: list[str]
    missing_from_target: list[str]
    diverged: list[str]
    target_newer: list[str]
    repo_newer: list[str]


def repo_skill_source(repo_root: Path) -> Path:
    return repo_root / "pipeline" / "autonomous.md"


def is_agent_source(path: Path) -> bool:
    """True for the shared guide, or a file whose `---` frontmatter has `name:` and `description:`.

    Anything else (specs, notes) in an agents dir is not an agent and is never rendered to a host.
    """
    if path.name == "AGENT_AGNOSTIC_GUIDE.md":
        return True
    parts = path.read_text().split("\n---\n", 1)
    if not parts[0].startswith("---\n") or len(parts) < 2:
        return False
    return all(re.search(rf"(?m)^{key}:[ \t]*\S", parts[0]) for key in ("name", "description"))


def repo_agent_sources(repo_root: Path) -> list[Path]:
    sources = sorted((repo_root / "agents").glob("*.md"))
    bundles_dir = repo_root / "agent_bundles"
    if bundles_dir.is_dir():
        sources.extend(sorted(bundles_dir.glob("*/agents/*.md")))
    sources = [source for source in sources if is_agent_source(source)]

    seen: dict[str, Path] = {}
    for source in sources:
        existing = seen.get(source.name)
        if existing is not None:
            raise ValueError(f"duplicate agent filename {source.name}: {existing} and {source}")
        seen[source.name] = source
    return sorted(sources, key=lambda source: source.name)


HOST_AGENTS_CONFIG = "host_agents.json"


def _split_host_agents(repo_root: Path, host: str | None) -> tuple[list[Path], list[Path]]:
    """(active, bench) agent sources for *host*, per `host_agents.json` (missing host or file => all active)."""
    sources = repo_agent_sources(repo_root)
    config_path = repo_root / HOST_AGENTS_CONFIG
    if host is None or not config_path.exists():
        return sources, []
    config = json.loads(config_path.read_text()).get(host, {})
    include = config.get("include", "all")
    exclude = set(config.get("exclude", []))
    named = exclude | (set() if include == "all" else set(include))
    unknown = named - {source.stem for source in sources}
    if unknown:
        raise ValueError(f"{HOST_AGENTS_CONFIG}[{host}] names unknown agents {sorted(unknown)}; use source file stems")
    active = [s for s in sources if (include == "all" or s.stem in include) and s.stem not in exclude]
    return active, [s for s in sources if s not in active]


def host_agent_sources(repo_root: Path, host: str | None) -> list[Path]:
    """Agent sources synced to *host*'s active agent dir."""
    return _split_host_agents(repo_root, host)[0]


def host_bench_sources(repo_root: Path, host: str | None) -> list[Path]:
    """Agent sources kept on *host*'s bench: synced to `agents-bench/`, which no host loads."""
    return _split_host_agents(repo_root, host)[1]


def bench_dir(agents_dir: Path) -> Path:
    return agents_dir.parent / "agents-bench"


def set_bench(repo_root: Path, stem: str, benched: bool, hosts: Sequence[str] | None = None) -> list[str]:
    """Bench (or play) *stem* for *hosts* (default: every host in `host_agents.json`); returns the hosts changed."""
    if stem not in {source.stem for source in repo_agent_sources(repo_root)}:
        raise ValueError(f"unknown agent {stem!r}; use a source file stem, e.g. pitch-agent")
    config_path = repo_root / HOST_AGENTS_CONFIG
    config = json.loads(config_path.read_text()) if config_path.exists() else {}
    changed = []
    for host in hosts or [key for key in config if key in HOST_NAMES]:
        entry = config.setdefault(host, {"include": "all", "exclude": []})
        exclude, include = entry.setdefault("exclude", []), entry.get("include", "all")
        if benched and stem not in exclude:
            entry["exclude"] = sorted(exclude + [stem])
        elif not benched and (stem in exclude or (include != "all" and stem not in include)):
            entry["exclude"] = [name for name in exclude if name != stem]
            if include != "all" and stem not in include:
                include.append(stem)
        else:
            continue
        changed.append(host)
    if changed:
        config_path.write_text(json.dumps(config, indent=2) + "\n")
    return changed


def rendered_agent_filename(source: Path) -> str:
    if source.name == "AGENT_AGNOSTIC_GUIDE.md":
        return source.name
    return f"aa_{source.stem.replace('-', '_')}.md"


def render_agent_prompt(source: Path) -> str:
    text = source.read_text()
    if source.name == "AGENT_AGNOSTIC_GUIDE.md":
        return text
    agent_name = f"aa_{source.stem.replace('-', '_')}"
    return re.sub(r"(?m)^name:\s*.+$", f"name: {agent_name}", text, count=1)


def repo_schema_sources(repo_root: Path) -> list[Path]:
    schemas_dir = repo_root / "schemas"
    if not schemas_dir.is_dir():
        return []
    return sorted(schemas_dir.glob("*.json"))


# Scripts that should be synced to host targets (validation tools, not repo-internal tooling).
_SYNCABLE_SCRIPTS = ("validate_quality_gate.py",)


def repo_script_sources(repo_root: Path) -> list[Path]:
    scripts_dir = repo_root / "scripts"
    if not scripts_dir.is_dir():
        return []
    return [scripts_dir / name for name in _SYNCABLE_SCRIPTS if (scripts_dir / name).exists()]


def load_dotenv(dotenv_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not dotenv_path.exists():
        return values

    for raw_line in dotenv_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        values[key] = os.path.expandvars(os.path.expanduser(value))
    return values


def discover_targets(repo_root: Path, env: dict[str, str]) -> list[HostTarget]:
    targets: list[HostTarget] = []
    for host in HOST_NAMES:
        prefix = host.upper()
        skill_path = env.get(f"{prefix}_SKILL_PATH")
        agents_dir = env.get(f"{prefix}_AGENTS_DIR")
        instructions_path = env.get(f"{prefix}_INSTRUCTIONS_PATH")
        config_snippet_path = env.get(f"{prefix}_CONFIG_SNIPPET_PATH")
        schemas_dir = env.get(f"{prefix}_SCHEMAS_DIR")
        scripts_dir = env.get(f"{prefix}_SCRIPTS_DIR")
        target = HostTarget(
            name=host,
            skill_path=Path(skill_path) if skill_path else None,
            agents_dir=Path(agents_dir) if agents_dir else None,
            instructions_path=Path(instructions_path) if instructions_path else None,
            config_snippet_path=Path(config_snippet_path) if config_snippet_path else None,
            schemas_dir=Path(schemas_dir) if schemas_dir else None,
            scripts_dir=Path(scripts_dir) if scripts_dir else None,
        )
        if not target.configured:
            continue
        targets.append(target)
    return targets


def _path_is_in_git_worktree(path: Path) -> bool:
    """Return True if writing *path* would touch a git-tracked file.

    Checks whether the specific destination (or any file underneath it, if
    *path* is a directory) is currently tracked by git. Untracked
    destinations are ALLOWED even when they sit inside a larger git repo —
    the sync only refuses when it would actually create a dirty tree.

    Two checks:

      1. ``git ls-files --error-unmatch <path>`` — returns 0 iff the exact
         path is a tracked file. Catches ``ANVIL_INSTRUCTIONS_PATH=/opt/anvil/
         AGENTS.md`` where AGENTS.md itself is committed.
      2. If *path* is a directory (existing or intended-to-be), check whether
         any tracked file lives underneath it via
         ``git -C <toplevel> ls-files -- <path-relative-to-toplevel>``. Catches
         ``ANVIL_AGENTS_DIR=/opt/anvil/agents`` where the dir exists AND
         contains tracked *.md files.

    Untracked paths inside otherwise-tracked repos (e.g. a fresh subdir
    under /opt/anvil the sync would create for the first time) do NOT
    match. Only paths git already knows about are protected.

    Behind the "sync must not write into git-tracked destinations" rule.
    Regression: [[project_opt_anvil_overlay_recurrence]].
    """
    probe = path if path.exists() else next(
        (parent for parent in path.parents if parent.exists()), None
    )
    if probe is None:
        return False

    # Establish the git toplevel (if any). Without one, path is definitely
    # not tracked.
    try:
        toplevel_result = subprocess.run(
            ["git", "-C", str(probe), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False
    if toplevel_result.returncode != 0 or not toplevel_result.stdout.strip():
        return False
    toplevel = Path(toplevel_result.stdout.strip())

    # Check 1: is `path` itself a tracked file?
    try:
        exact_result = subprocess.run(
            ["git", "-C", str(toplevel), "ls-files", "--error-unmatch", str(path)],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False
    if exact_result.returncode == 0:
        return True

    # Check 2: if `path` is (or will be) a directory, are ANY tracked files
    # underneath it?
    try:
        should_relativize = (path.is_absolute() and toplevel in path.parents) or path == toplevel
        rel_path = path.relative_to(toplevel) if should_relativize else path
    except ValueError:
        rel_path = path
    try:
        subtree_result = subprocess.run(
            [
                "git", "-C", str(toplevel), "ls-files", "--", str(rel_path),
            ],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False
    return subtree_result.returncode == 0 and bool(subtree_result.stdout.strip())


def _target_is_git_managed(target: HostTarget) -> bool:
    """Return True if any of *target*'s configured paths lives in a git worktree."""
    candidates = [
        target.skill_path,
        target.agents_dir,
        target.instructions_path,
        target.config_snippet_path,
        target.schemas_dir,
        target.scripts_dir,
    ]
    return any(p is not None and _path_is_in_git_worktree(p) for p in candidates)


def sync_target(repo_root: Path, target: HostTarget) -> bool:
    """Sync *target*. Returns True when the sync ran, False when it was skipped.

    Skipped when the target's destination paths are git-tracked — see
    ``_path_is_in_git_worktree`` for the definition. In that case, prints a
    warning and returns False so the caller can distinguish "no-op skip"
    from "wrote files."
    """
    if _target_is_git_managed(target):
        # Git-managed host targets (e.g. ANVIL_* pointing at /opt/anvil, which
        # is a git checkout with tracked prompt-pack files) MUST update their
        # prompt-pack files via their own repo's release flow, not via this
        # sync. Writing here creates a dirty working tree that blocks that
        # repo's own updater. See [[project_opt_anvil_overlay_recurrence]].
        print(
            f"sync_target: SKIPPED host '{target.name}' -- destination has git-tracked "
            f"files. That repo owns them; update via its own release flow.",
        )
        return False

    if target.skill_path and target.agents_dir:
        target.skill_path.parent.mkdir(parents=True, exist_ok=True)
        target.agents_dir.mkdir(parents=True, exist_ok=True)

        target.skill_path.write_text(repo_skill_source(repo_root).read_text())
        sync_agents_dir(repo_root, target.agents_dir, target.name)

    if target.schemas_dir:
        target.schemas_dir.mkdir(parents=True, exist_ok=True)
        schema_sources = repo_schema_sources(repo_root)
        source_names = {s.name for s in schema_sources}
        for target_file in target.schemas_dir.glob("*.json"):
            if target_file.name not in source_names:
                target_file.unlink()
        for source in schema_sources:
            (target.schemas_dir / source.name).write_text(source.read_text())

    if target.scripts_dir:
        target.scripts_dir.mkdir(parents=True, exist_ok=True)
        for source in repo_script_sources(repo_root):
            dest = target.scripts_dir / source.name
            dest.write_text(source.read_text())
            dest.chmod(0o755)

    if target.instructions_path:
        target.instructions_path.parent.mkdir(parents=True, exist_ok=True)
        target.instructions_path.write_text(render_host_instructions(repo_root, target))

    if target.config_snippet_path:
        snippet = render_host_config_snippet(repo_root, target)
        if snippet:
            target.config_snippet_path.parent.mkdir(parents=True, exist_ok=True)
            target.config_snippet_path.write_text(snippet)

    return True


def sync_agents_dir(repo_root: Path, agents_dir: Path, host: str | None = None) -> None:
    active, bench = _split_host_agents(repo_root, host)
    _write_agents(agents_dir, active)
    if bench or bench_dir(agents_dir).is_dir():
        _write_agents(bench_dir(agents_dir), bench)


def _write_agents(agents_dir: Path, sources: list[Path]) -> None:
    agents_dir.mkdir(parents=True, exist_ok=True)
    rendered_names = {rendered_agent_filename(source) for source in sources}
    for target_file in agents_dir.glob("*.md"):
        if target_file.name not in rendered_names:
            target_file.unlink()
    for source in sources:
        (agents_dir / rendered_agent_filename(source)).write_text(render_agent_prompt(source))


def check_target(repo_root: Path, target: HostTarget) -> SyncStatus:
    skill_source = repo_skill_source(repo_root)
    agent_sources = host_agent_sources(repo_root, target.name)
    skill_in_sync: bool | None = None
    missing_agents: list[str] | None = None
    bench: list[str] | None = None
    bench_problems: list[str] | None = None
    if target.agents_dir:
        bench, bench_problems = [], []
        for source in host_bench_sources(repo_root, target.name):
            name = rendered_agent_filename(source)
            bench.append(name)
            if (target.agents_dir / name).exists():
                bench_problems.append(f"{name}(active)")
            benched_file = bench_dir(target.agents_dir) / name
            if not benched_file.exists() or benched_file.read_text() != render_agent_prompt(source):
                bench_problems.append(f"{name}(missing)")
    if target.skill_path or target.agents_dir:
        if not target.skill_path or not target.agents_dir or not target.skill_path.exists() or not target.agents_dir.exists():
            skill_in_sync = False
            missing_agents = [source.name for source in agent_sources]
        else:
            skill_in_sync = sha256_file(skill_source) == sha256_file(target.skill_path)
            missing_agents = []
            for source in agent_sources:
                target_file = target.agents_dir / rendered_agent_filename(source)
                if not target_file.exists() or render_agent_prompt(source) != target_file.read_text():
                    missing_agents.append(rendered_agent_filename(source))

    instructions_in_sync: bool | None = None
    if target.instructions_path:
        instructions_in_sync = (
            target.instructions_path.exists()
            and target.instructions_path.read_text() == render_host_instructions(repo_root, target)
        )

    config_snippet_in_sync: bool | None = None
    if target.config_snippet_path:
        expected = render_host_config_snippet(repo_root, target)
        config_snippet_in_sync = target.config_snippet_path.exists() and target.config_snippet_path.read_text() == expected

    missing_schemas: list[str] | None = None
    if target.schemas_dir:
        missing_schemas = []
        for source in repo_schema_sources(repo_root):
            target_file = target.schemas_dir / source.name
            if not target_file.exists() or sha256_file(source) != sha256_file(target_file):
                missing_schemas.append(source.name)

    missing_scripts: list[str] | None = None
    if target.scripts_dir:
        missing_scripts = []
        for source in repo_script_sources(repo_root):
            target_file = target.scripts_dir / source.name
            if not target_file.exists() or sha256_file(source) != sha256_file(target_file):
                missing_scripts.append(source.name)

    return SyncStatus(
        host=target.name,
        configured=True,
        skill_in_sync=skill_in_sync,
        instructions_in_sync=instructions_in_sync,
        config_snippet_in_sync=config_snippet_in_sync,
        missing_agents=missing_agents,
        missing_schemas=missing_schemas,
        missing_scripts=missing_scripts,
        bench=bench,
        bench_problems=bench_problems,
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def agent_inventory_for_dir(agents_dir: Path) -> dict[str, AgentFile]:
    if not agents_dir.is_dir():
        return {}
    inventory: dict[str, AgentFile] = {}
    for path in sorted(agents_dir.glob("*.md")):
        stat = path.stat()
        inventory[path.name] = AgentFile(
            name=path.name,
            path=path,
            sha256=sha256_file(path),
            mtime_ns=stat.st_mtime_ns,
        )
    return inventory


def canonical_agent_filename(filename: str) -> str:
    if filename == "AGENT_AGNOSTIC_GUIDE.md" or filename.startswith("aa_"):
        return filename
    path = Path(filename)
    return f"aa_{path.stem.replace('-', '_')}{path.suffix}"


def canonical_agent_prompt_text(path: Path, canonical_name: str) -> str:
    text = path.read_text()
    if canonical_name == "AGENT_AGNOSTIC_GUIDE.md":
        return text
    agent_name = Path(canonical_name).stem
    return re.sub(r"(?m)^name:\s*.+$", f"name: {agent_name}", text, count=1)


def canonical_agent_inventory_for_dir(agents_dir: Path) -> dict[str, AgentFile]:
    inventory: dict[str, AgentFile] = {}
    for agent in agent_inventory_for_dir(agents_dir).values():
        canonical_name = canonical_agent_filename(agent.name)
        canonical_text = canonical_agent_prompt_text(agent.path, canonical_name)
        canonical_sha = hashlib.sha256(canonical_text.encode()).hexdigest()
        canonical_agent = AgentFile(
            name=agent.name,
            path=agent.path,
            sha256=canonical_sha,
            mtime_ns=agent.mtime_ns,
        )
        if canonical_name in inventory:
            existing = inventory[canonical_name]
            if agent.mtime_ns <= existing.mtime_ns:
                continue
        inventory[canonical_name] = canonical_agent
    return inventory


def repo_agent_inventory(repo_root: Path, host: str | None = None) -> dict[str, AgentFile]:
    inventory: dict[str, AgentFile] = {}
    for source in host_agent_sources(repo_root, host):
        stat = source.stat()
        rendered_name = rendered_agent_filename(source)
        rendered_text = render_agent_prompt(source)
        digest = hashlib.sha256(rendered_text.encode()).hexdigest()
        inventory[rendered_name] = AgentFile(
            name=rendered_name,
            path=source,
            sha256=digest,
            mtime_ns=stat.st_mtime_ns,
        )
    return inventory


def reconcile_agent_inventory(repo_root: Path, target_agents_dir: Path, host: str | None = None) -> AgentInventoryReport:
    repo_inventory = repo_agent_inventory(repo_root, host)
    target_inventory = canonical_agent_inventory_for_dir(target_agents_dir)
    repo_names = set(repo_inventory)
    target_names = set(target_inventory)
    common_names = sorted(repo_names & target_names)

    diverged: list[str] = []
    target_newer: list[str] = []
    repo_newer: list[str] = []
    for name in common_names:
        repo_agent = repo_inventory[name]
        target_agent = target_inventory[name]
        if repo_agent.sha256 == target_agent.sha256:
            continue
        diverged.append(name)
        if target_agent.mtime_ns > repo_agent.mtime_ns:
            target_newer.append(name)
        elif repo_agent.mtime_ns > target_agent.mtime_ns:
            repo_newer.append(name)

    return AgentInventoryReport(
        repo_count=len(repo_inventory),
        target_count=len(agent_inventory_for_dir(target_agents_dir)),
        missing_from_repo=sorted(target_inventory[name].name for name in (target_names - repo_names)),
        missing_from_target=sorted(repo_names - target_names),
        diverged=diverged,
        target_newer=target_newer,
        repo_newer=repo_newer,
    )


def format_agent_inventory_report(label: str, report: AgentInventoryReport) -> str:
    lines = [
        f"{label}: repo={report.repo_count} target={report.target_count}",
        f"  missing_from_repo={len(report.missing_from_repo)}",
        f"  missing_from_target={len(report.missing_from_target)}",
        f"  diverged={len(report.diverged)}",
        f"  target_newer={len(report.target_newer)}",
        f"  repo_newer={len(report.repo_newer)}",
    ]
    for field_name in (
        "missing_from_repo",
        "missing_from_target",
        "diverged",
        "target_newer",
        "repo_newer",
    ):
        values = getattr(report, field_name)
        if values:
            lines.append(f"  {field_name}: {', '.join(values)}")
    return "\n".join(lines)


def host_capabilities() -> dict[str, tuple[str, ...]]:
    return {name: spec.capability_tags for name, spec in HOST_SPECS.items()}


CONTRACT_REFERENCE = "~/_CODING/autonomous_agents_mds/docs/contract-reference.md"

# One compact line per host; everything host-agnostic is shared.
_HOST_NOTES = {
    "claude": "Claude: run `/superpowers` (or `superpowers:using-superpowers`) and proactively suggest matching MCP servers/skills (Drive, M365, Asana, Anvil, agent-memory, WebSearch). Hooks/plugins handle memory capture.",
    "codex": "Codex: use installed Superpowers skills, MCP and explicit sub-agent delegation; this file is the global contract, the synced pack is the specialist library.",
    "gemini": "Gemini: `activate_skill`; project `GEMINI.md` + MCP; the synced pack holds the specialist contracts.",
    "anvil": "Anvil: production execution platform; use its local skills/tools, MCP server and FastAPI surface (quality-gate automation, workflow promotion).",
}

# Recency bias: models weight the END of the context most. This block MUST stay last
# (tests/test_context_budget.py); the first lines of the file point to it.
IRON_RULES_HEADING = "## Iron Rules (top priority; last on purpose, they override everything above)"
_IRON_RULES = [
    IRON_RULES_HEADING,
    "1. **Root cause, never symptom §RC.** Before calling anything fixed, name the MECHANISM (line, key, column, missing guard), why checks missed it, where else it lives, and what prevents recurrence (a test seen FAILING on the unfixed code, or a constraint). MUST NOT, unless the operator chooses it: widen a limit, swallow an exception, skip/xfail a real failing test, edit an installed copy or a generated file, loosen a true assertion. Root fix out of scope: minimal reversible mitigation, labelled as such, plus an issue.",
    "2. **Done = verified end state §DD.** State acceptance criteria up front; query/curl/measure the live system and hold the output. No self-certification: a separate auditor (and QA for UI). Partial = PARTIAL, never DONE.",
    "3. **Secrets §SEC.** Runtime-injected only, never in an image, config file or git; rotatable in minutes (create new, migrate writers, revoke old); secret scanning in EVERY lane (local and CI).",
    "4. **Human release gate §HG.** Operator approval is still required for production deploys outside the repo's CI deployer, DNS/IAM/credential changes, destructive production data changes, and every human-gated merge (§BR).",
    "5. **OPTIMIZE EVERYTHING §OPT.** Ship faster, spend less: measure first, then cut; smallest change, fewest steps; maintained libraries over new code; keep the safety floor (validation, secrets, backups, green CI, e2e gates). GitHub bills the WFCA card: no GitHub-billed usage for personal projects, run checks locally first. Answer first, briefly; keep tool output small. Tokens cost money.",
]


def render_host_instructions(repo_root: Path, target: HostTarget) -> str:
    spec = HOST_SPECS[target.name]
    skill_path = target.skill_path or repo_root / "pipeline" / "autonomous.md"
    agents_dir = target.agents_dir or repo_root / "agents"
    lines = [
        f"# {spec.instruction_filename}",
        "",
        "Top-priority Iron Rules are the LAST section of this file; they override everything above.",
        f"`§XX` = that section of `{CONTRACT_REFERENCE}` (full rules; read it when a rule applies).",
        "",
        "You are a top senior engineer working in the fire service: detail-oriented, autonomous, professionally finished work (enterprise background: Intel, Jeld-Wen, Microsoft, Bank of America, Ebay).",
        "YOU ARE AN ORCHESTRATOR OF DEVELOPMENT TEAMS AND AGENTS. Work autonomously within project and org rules; self-prioritize GitHub issues by business value into sprints.",
        "**ALWAYS DISPATCH AGENTS IN PERSONAL WORKTREE.** Subagent-driven by default: a fresh subagent per multi-step task; inline only for one command or a sub-2-minute edit. §OM",
        "You have an agent memory tool; use it. An auto git committer may checkpoint edits; inspect the worktree before publishing.",
        "Generated by `scripts/sync_prompt_pack.py`; never hand-edit this installed copy, edit the source repo and re-sync.",
        "",
        "## Setup §SS",
        f"- Pipeline prompt `{skill_path}`; specialist prompts `{agents_dir}`; capabilities: {', '.join(spec.capability_tags)}.",
        "- Prompt pack source: `~/_CODING/autonomous_agents_mds/` (canonical; `~/_CODING/` is the source of truth, `~/Dropbox/_CODING/` a backup only). Hooks source: `~/_CODING/hooks/`. Installed agent dirs are never canonical.",
        f"- Git distribution source: `{DEFAULT_REPO_URL}`",
        "- Prompt pack sync: `cd ~/_CODING/autonomous_agents_mds && PYTHONPATH=. python3 scripts/sync_prompt_pack.py sync`",
        f"- Session start: discover skills and invoke the matching workflow skill. {_HOST_NOTES.get(target.name, '')}".rstrip(),
        "- Read README, `.autonomous.json`, `todo.json` and project/nested `CLAUDE.md`/`AGENTS.md`/`GEMINI.md`; they override this file where they define branching, QA or deploy. Durable guidance in instruction files; ephemeral status in `HANDOFF.md`/tracker.",
        "- Session-handoff markers (agent-agnostic): process `plans/session-handoff/*` (not `processed/`) first: land or keep each branch, move the marker to `processed/`; older than 7 days: open an issue, ping a human.",
        "",
        "## Operating model §OM",
        "- Tasks: `todo.json` + GitHub Issues; lessons to agentMemory. Every issue has acceptance criteria; done needs an auditor and (UI) a QA agent.",
        "- Out-of-scope problem, no blame: trivial and in a touched file, fix now; bounded, dispatch a worktree subagent; larger, log it (Asana primary, GitHub fallback). Never silently drop.",
        "- Non-trivial plan: `quality-gate` specialist first, validated by `scripts/validate_quality_gate.py`. CODE_REVIEW before TEST; enforce DRY, simplification, naming.",
        "- Migrations are IMMUTABLE once applied to a shared env: fix forward in a new migration; checksum re-align only via guarded `reconcile` after verifying the live DB.",
        "- Docs (CHANGELOG, CLAUDE.md, ARCHITECTURE, AGENTS.md, HANDOFF) every sprint; post-sprint `/improve` + memory notes are MANDATORY. Omit `Co-Authored-By` lines. Daily compact evidence/blocker summary.",
        "- Automate and make everything easier as you go; you may extend yourself. Code securely.",
        "",
        "## Incidents §IN",
        "Emergencies tighten process: root-cause first (`superpowers:systematic-debugging`; after 2 failed fixes run the one diagnostic that isolates the layer); dev first, prod gets only a minimal reversible stop-the-bleed; snapshot and write the revert first; migrations via the runner; one verified fix at a time; closed only when durably stable and audited. Never relabel prod in place (§HG).",
        "",
        "## Branching & Integration (enforced by hooks; if hooks are not present, create them) §BR",
        "- `<trunk>` = `main` else `master`. Single-trunk ONLY if `origin/<trunk>` has `.reconcile-gate.json` `{\"model\":\"single-trunk\"}`: feature branch (own worktree) → squash PR → `<trunk>`. Otherwise legacy two-trunk: land on `dev`/`develop` via `/reconcile`, PRs only integration → production; neither trunk: STOP and ask. The reconciler never creates `dev`.",
        "- Merge needs ALL: CI green; independent review (§CR); `aa_auditor` PASS; end-to-end run pasted; one PR comment for the CURRENT head SHA with `review: APPROVE <sha>` and `audit: PASS <sha>` plus both verdicts quoted. The ORCHESTRATING agent posts it, never the implementer, reviewer or auditor for its own work.",
        "- Merge only via `gh pr merge <pr> --squash --match-head-commit <headRefOid>` after `gh pr checks` shows every check (incl. `agent-gate`) passing; GitHub refuses: STOP.",
        "- **Self-merge permission (fail closed):** only if, in the same run, branch protection POSITIVELY shows `required_approving_review_count == 0` AND `agent-gate` required, and no CODEOWNERS; anything else (404, 403, error) is human-gated: open the PR, attach evidence, STOP. An unprotected trunk is human-gated.",
        "- MUST NOT: `gh pr merge --admin`; approve your own PR; push or force-push `<trunk>`; `--no-verify`; a second deploy path; self-merge changes to `.reconcile-gate.json`, `.github/workflows/agent-gate*`, CODEOWNERS or `.github/rulesets/**`; `--force-anyway` without asking the user.",
        "",
        "## Code review §CR",
        "Mandatory before any merge/reconcile and for high-blast-radius diffs (build, CI, IaC, hooks, manifests); a separate context, never self-review. Cascade: `codex review --base origin/<trunk>` (or `--uncommitted`), then Anvil `aa_code_reviewer`, then Claude `aa_code_reviewer`. Findings verbatim; blocking findings block. All three fail: STOP and ask.",
        "",
        "## Issue pipeline & audit §IP",
        "One GitHub issue with testable criteria → one branch `work/issue-<n>-<slug>` in its own worktree. Before merge, a fresh-context `aa_auditor` checks every criterion from GitHub against the live end state; any unmet, partial or unverifiable criterion = FAIL, loop back on the same branch. The implementer never audits itself or rewrites criteria. On PASS + merge, record evidence and close the issue citing the commit.",
        "",
        *_IRON_RULES,
        "",
    ]
    return "\n".join(lines)


def render_host_config_snippet(repo_root: Path, target: HostTarget) -> str:
    if target.name == "codex":
        return (
            '# Generated by scripts/sync_prompt_pack.py\n'
            f'[projects."{repo_root}"]\n'
            'trust_level = "trusted"\n\n'
            "[mcp_servers.agent-memory]\n"
            'command = "/path/to/agentMemory/.venv/bin/python"\n'
            'args = ["/path/to/agentMemory/mcp_server.py"]\n'
        )
    if target.name == "claude":
        return (
            "{\n"
            '  "hooks": {\n'
            '    "SessionStart": [\n'
            '      {\n'
            '        "hooks": [\n'
            '          {\n'
            '            "type": "command",\n'
            f'            "command": "cd {repo_root} && python3 scripts/sync_prompt_pack.py update-and-sync --repo-root {repo_root}",\n'
            '            "timeout": 30\n'
            "          }\n"
            "        ]\n"
            "      }\n"
            "    ]\n"
            "  }\n"
            "}\n"
        )
    if target.name == "gemini":
        return (
            "{\n"
            '  "mcpServers": {\n'
            '    "agent-memory": {\n'
            '      "command": "/path/to/agentMemory/.venv/bin/python",\n'
            '      "args": ["/path/to/agentMemory/mcp_server.py"]\n'
            "    }\n"
            "  }\n"
            "}\n"
        )
    if target.name == "anvil":
        return (
            "{\n"
            '  "mcpServers": {\n'
            '    "agent-memory": {\n'
            '      "command": "/path/to/agentMemory/.venv/bin/python",\n'
            '      "args": ["/path/to/agentMemory/mcp_server.py"]\n'
            "    }\n"
            "  }\n"
            "}\n"
        )
    return ""


def feature_report() -> str:
    lines = ["Host feature matrix:"]
    for name in HOST_NAMES:
        spec = HOST_SPECS[name]
        config_mode = spec.config_format or "none"
        lines.append(f"- {name}: instructions={spec.instruction_filename} config={config_mode} capabilities={','.join(spec.capability_tags)}")
    return "\n".join(lines)


def cron_line(repo_root: Path, python_bin: str = "python3") -> str:
    script = repo_root / "scripts" / "sync_prompt_pack.py"
    return f"*/15 * * * * cd {shell_escape(str(repo_root))} && {shell_escape(python_bin)} {shell_escape(str(script))} update-and-sync --repo-root {shell_escape(str(repo_root))} >/dev/null 2>&1"


def anacron_line(repo_root: Path, python_bin: str = "python3") -> str:
    script = repo_root / "scripts" / "sync_prompt_pack.py"
    return f"15 10 autonomous-prompt-pack cd {shell_escape(str(repo_root))} && {shell_escape(python_bin)} {shell_escape(str(script))} update-and-sync --repo-root {shell_escape(str(repo_root))} >/dev/null 2>&1"


def windows_task_command(repo_root: Path, python_bin: str = "python") -> str:
    script = repo_root / "scripts" / "sync_prompt_pack.py"
    return f'{python_bin} "{script}" update-and-sync --repo-root "{repo_root}"'


def launchd_plist(repo_root: Path, python_bin: str = "python3", label: str = "com.metazen11.autonomous-prompt-pack-sync") -> str:
    script = repo_root / "scripts" / "pull-and-sync.sh"
    log_dir = repo_root / ".runs" / "logs"
    stdout_path = log_dir / "launchd-stdout.log"
    stderr_path = log_dir / "launchd-stderr.log"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>{label}</string>
    <key>WorkingDirectory</key>
    <string>{repo_root}</string>
    <key>ProgramArguments</key>
    <array>
      <string>/bin/bash</string>
      <string>{script}</string>
    </array>
    <key>StartInterval</key>
    <integer>900</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{stdout_path}</string>
    <key>StandardErrorPath</key>
    <string>{stderr_path}</string>
    <key>EnvironmentVariables</key>
    <dict>
      <key>PATH</key>
      <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
    </dict>
  </dict>
</plist>
"""


def windows_task_xml(repo_root: Path, python_bin: str = "python", author: str = "metazen11") -> str:
    script = repo_root / "scripts" / "sync_prompt_pack.py"
    command = python_bin
    arguments = f'"{script}" update-and-sync --repo-root "{repo_root}"'
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Author>{author}</Author>
    <Description>Sync autonomous prompt pack into configured host directories.</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <Repetition>
        <Interval>PT15M</Interval>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
      <StartBoundary>2026-01-01T09:00:00</StartBoundary>
      <Enabled>true</Enabled>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{command}</Command>
      <Arguments>{arguments}</Arguments>
      <WorkingDirectory>{repo_root}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def install_from_git_command(
    repo_url: str = DEFAULT_REPO_URL,
    install_dir: Path = DEFAULT_INSTALL_DIR,
    branch: str = "main",
    python_bin: str = "python3",
) -> str:
    install_dir = install_dir.expanduser()
    parent = install_dir.parent
    return (
        f"mkdir -p {shell_escape(str(parent))} && "
        f"if [ ! -d {shell_escape(str(install_dir / '.git'))} ]; then "
        f"git clone {shell_escape(repo_url)} {shell_escape(str(install_dir))}; "
        f"fi && "
        f"cd {shell_escape(str(install_dir))} && "
        f"git fetch origin {shell_escape(branch)} && "
        f"git checkout {shell_escape(branch)} && "
        f"git pull --ff-only origin {shell_escape(branch)} && "
        f"PYTHONPATH=. {shell_escape(python_bin)} scripts/sync_prompt_pack.py sync"
    )


def update_checkout_from_git(
    repo_url: str = DEFAULT_REPO_URL,
    install_dir: Path = DEFAULT_INSTALL_DIR,
    branch: str = "main",
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> None:
    install_dir = install_dir.expanduser()
    if not (install_dir / ".git").is_dir():
        install_dir.parent.mkdir(parents=True, exist_ok=True)
        run_git_command(runner, ["git", "clone", "--branch", branch, repo_url, str(install_dir)])
        return

    run_git_command(runner, ["git", "-C", str(install_dir), "fetch", "origin", branch])
    run_git_command(runner, ["git", "-C", str(install_dir), "checkout", branch])
    run_git_command(runner, ["git", "-C", str(install_dir), "pull", "--ff-only", "origin", branch])


def run_git_command(
    runner: Callable[..., subprocess.CompletedProcess[str]],
    command: Sequence[str],
) -> subprocess.CompletedProcess[str]:
    return runner(command, check=True, text=True)


def install_git_hooks(repo_root: Path, python_bin: str = "python3") -> list[Path]:
    hooks_dir = repo_root / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    script = repo_root / "scripts" / "sync_prompt_pack.py"
    body = (
        "#!/usr/bin/env sh\n"
        "# Auto-generated by scripts/sync_prompt_pack.py\n"
        f"cd {shell_escape(str(repo_root))} || exit 0\n"
        f"{shell_escape(python_bin)} {shell_escape(str(script))} update-and-sync --repo-root {shell_escape(str(repo_root))} >/dev/null 2>&1 || true\n"
    )
    written: list[Path] = []
    for hook_name in ("post-merge", "post-checkout"):
        hook_path = hooks_dir / hook_name
        hook_path.write_text(body)
        hook_path.chmod(0o755)
        written.append(hook_path)
    return written


def shell_escape(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"

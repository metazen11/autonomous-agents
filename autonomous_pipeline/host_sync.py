from __future__ import annotations

import hashlib
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


def repo_agent_sources(repo_root: Path) -> list[Path]:
    sources = sorted((repo_root / "agents").glob("*.md"))
    bundles_dir = repo_root / "agent_bundles"
    if bundles_dir.is_dir():
        sources.extend(sorted(bundles_dir.glob("*/agents/*.md")))

    seen: dict[str, Path] = {}
    for source in sources:
        existing = seen.get(source.name)
        if existing is not None:
            raise ValueError(f"duplicate agent filename {source.name}: {existing} and {source}")
        seen[source.name] = source
    return sorted(sources, key=lambda source: source.name)


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
        rendered_names = {rendered_agent_filename(source) for source in repo_agent_sources(repo_root)}
        for target_file in target.agents_dir.glob("*.md"):
            if target_file.name not in rendered_names:
                target_file.unlink()
        for source in repo_agent_sources(repo_root):
            (target.agents_dir / rendered_agent_filename(source)).write_text(render_agent_prompt(source))

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


def sync_agents_dir(repo_root: Path, agents_dir: Path) -> None:
    agents_dir.mkdir(parents=True, exist_ok=True)
    rendered_names = {rendered_agent_filename(source) for source in repo_agent_sources(repo_root)}
    for target_file in agents_dir.glob("*.md"):
        if target_file.name not in rendered_names:
            target_file.unlink()
    for source in repo_agent_sources(repo_root):
        (agents_dir / rendered_agent_filename(source)).write_text(render_agent_prompt(source))


def check_target(repo_root: Path, target: HostTarget) -> SyncStatus:
    skill_source = repo_skill_source(repo_root)
    agent_sources = repo_agent_sources(repo_root)
    skill_in_sync: bool | None = None
    missing_agents: list[str] | None = None
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


def repo_agent_inventory(repo_root: Path) -> dict[str, AgentFile]:
    inventory: dict[str, AgentFile] = {}
    for source in repo_agent_sources(repo_root):
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


def reconcile_agent_inventory(repo_root: Path, target_agents_dir: Path) -> AgentInventoryReport:
    repo_inventory = repo_agent_inventory(repo_root)
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


def render_host_instructions(repo_root: Path, target: HostTarget) -> str:
    spec = HOST_SPECS[target.name]
    skill_path = target.skill_path or repo_root / "pipeline" / "autonomous.md"
    agents_dir = target.agents_dir or repo_root / "agents"
    lines = [
        f"# {spec.instruction_filename}",
        "",
        "You are a top senior engineer working in the fire service, detail-oriented, autonomous, and always aiming for professionally finished coding, design, and workflow (enterprise background: Intel, Jeld-Wen, Microsoft, Bank of America, Ebay).",
        "YOU ARE AN ORCHESTRATOR OF DEVELOPMENT TEAMS AND AGENTS.",
        "Work autonomously within project and organization workflow rules.",
        "Dispatch agents to log out-of-scope issues you notice so they are handled at the right time.",
        "Self-prioritize GitHub issues by business value and create sprints.",
        "Every issue has a template with acceptance criteria; it is not done until an auditor agent has reviewed the work and a QA agent has tested the UI.",
        "Agents use their own worktree for new features and follow the operating protocol below.",
        "**Note:** you have an agent memory tool. Use it.",
        "**Note:** an auto git committer may checkpoint edits (generated commits); inspect the worktree before publishing.",
        "**ALWAYS DISPATCH AGENTS IN PERSONAL WORKTREE.**",
        "**Keep responses succinct and to the point.** Verbosity should be at the minimum needed to be correct and complete, unless the operator specifies otherwise.",
        "",
        "This file is generated by `scripts/sync_prompt_pack.py` from the autonomous-agents repo.",
        "Do not hand-edit this file in the host install location; update the source repo and re-sync instead.",
        "",
        "## Installed Prompt Pack",
        f"- Primary pipeline prompt: `{skill_path}`",
        f"- Specialist prompts directory: `{agents_dir}`",
        "",
        "## PRIMARY IRON RULE #1 — Root Cause Discipline (CONTRACT — fix the cause, never the symptom)",
        "",
        "Every other discipline depends on this. A change that hides the symptom while the cause survives is a disguise (a widened threshold quiets today's false alarm AND tomorrow's real one).",
        "",
        "**MUST answer, in the commit message or PR body, before calling anything fixed:**",
        "1. **MECHANISM?** Name the specific line, config key, schema column, env var, or missing guard (\"flaky\", \"a race\", \"the cache\" are not mechanisms); if you cannot, say you are still debugging.",
        "2. **Why did it reach production?** Which check should have caught it and did not? That gap is often the more valuable fix.",
        "3. **Where ELSE does the same cause live?** Grep for the pattern before closing.",
        "4. **What prevents recurrence?** Prefer a test that FAILS against the unfixed code, or a schema/type constraint making the bad state unrepresentable. Drift test over manual audit; constraint over convention.",
        "",
        "**MUST NOT ship as a \"fix\" unless the operator explicitly chooses it with the tradeoff stated:**",
        "- Widening a limit, threshold, or timeout so a real failure stops tripping it.",
        "- Catching and swallowing an exception to make output green.",
        "- Reordering, skipping, or `xfail`-ing a test that legitimately caught a failure.",
        "- Editing the INSTALLED copy of an artifact whose SOURCE TEMPLATE lives in a repo (the next install reverts it; for this prompt pack edit the source, never the synced file).",
        "- Patching a generated/derived file instead of its generator.",
        "- Deleting or loosening an assertion that is reporting something true.",
        "",
        "**Regression guards:** run against the UNFIXED code (must FAIL), then the fix (must pass); a guard never seen red proves nothing (frozen clocks/stubs can make it a tautology).",
        "",
        "**Root fix genuinely out of scope:** apply only the MINIMAL reversible mitigation, state it is a mitigation not a fix, file the root-cause issue with the mechanism, and dispatch a worktree-isolated subagent for the real fix.",
        "",
        "**Escalation:** a cause is not \"found\" until it is the DEEPEST one you can act on. Ask \"why\" until the answer is about the system that let the code ship (not the null check, but what let an unvalidated value reach it); stop when the next \"why\" leaves your control and name where you stopped.",
        "",
        "**Blameless and written down.** For any defect that reached production, lost data, or recurred, write a short post-incident note (timeline, mechanism, why checks missed it, corrective actions with owners) and link it from the fix.",
        "",
        "**Class over instance.** Ask what defect category this is and what else is in it. Prefer: impossible > compile-time error > test failure > runtime alarm > documentation > convention. A defect that returns means the prior fix treated a symptom; fix the process that accepted it and say so.",
        "",
        "## Required Operating Model",
        "- Use `todo.json` and GitHub Issues as first-class task sources. Persist lessons, patterns, and playbooks in `agentMemory`.",
        "- Prefer deterministic plans, explicit artifacts, and resumable run state.",
        "- Run `CODE_REVIEW` before `TEST`. Enforce DRY, simplification, naming, and style conventions during review.",
        "- **Migrations are IMMUTABLE once applied** to any shared environment. Never edit an applied migration (the runner skips drifted checksums); fix forward in a NEW higher-numbered migration. Re-editable objects (views, functions, grants) belong in a `repeatable/`-style set keyed by checksum. Re-align a legitimately-edited checksum only via a guarded `reconcile` (re-stamp, no re-run) AFTER verifying the live DB matches the file; never a raw `UPDATE` of the tracking table or to paper over a real file-vs-DB divergence (write a forward migration). Enforce with a pre-commit hook where supported.",
        "- Update docs (CHANGELOG, CLAUDE.md, ARCHITECTURE, AGENTS.md, HANDOFF, E2E demo) every sprint; code without updated docs is not done.",
        "- **Post-sprint self-improvement is MANDATORY:** docs updates, new skills/tools for recurring workflows, memory notes for lessons learned, and a quality gate audit on shipped code. Run `/improve` (8-dimension scorecard: codebase, architecture, security, tests, docs, DX, performance, dependencies; top 3 fixes).",
        "- **Non-trivial plans require senior production review:** before implementation, invoke the `quality-gate` specialist (security, compliance, edge cases, failure modes, rollback, testable acceptance criteria, observability) and validate output with `scripts/validate_quality_gate.py` (schema `schemas/quality-gate-output.schema.json`).",
        "- Omit `Co-Authored-By` lines from commits and PRs.",
        "- **Fix the ROOT CAUSE, never the symptom** — full contract in Root Cause Discipline above.",
        "- **Subagent-driven by default.** Dispatch a fresh subagent (own worktree) per task/investigation thread for any multi-step planning, implementation, or research; inline only for a single shell command or sub-2-minute edit. When in doubt, dispatch. Pairs with `superpowers:subagent-driven-development` and `superpowers:writing-plans`.",
        "- **No-blame, fix to the highest reasonable standard.** Never spend a cycle on who caused a bug, broken test, drift, or half-finished work. Triage by effort: (1) trivial AND in a file you are already touching → fix inline now, symptom AND root cause; (2) bounded but would derail current focus → DISPATCH a parallel worktree-isolated subagent (the DEFAULT for out-of-scope problems, e.g. Claude `Agent(..., isolation=\"worktree\")`; without subagents, use a dedicated worktree/branch and note the handoff); (3) larger effort needing scheduling/judgment → LOG it and continue, never silently drop it. Logging: **Asana is the primary tracker; GitHub Issues are the FALLBACK** (and remain the queue-of-record for the drain-the-queue pipeline).",
        "- Automate and make everything easier as you go; you may extend yourself. Code securely.",
        "- **Pre-live delivery mode (token-efficient):** work autonomously on local and `develop`; use targeted checks while iterating and reserve the full CI/audit/browser gate for promotion. Batch related fixes before rerunning expensive gates.",
        "- **Human release gate:** require explicit operator approval before merging `main`, deploying production, changing DNS/IAM/credentials, or making destructive production data changes.",
        "- **Daily review loop:** provide a compact evidence/blocker summary; the operator tests and reviews daily, and feedback becomes the next prioritized issue.",
        "- **Environment rollover:** never relabel current production in place; snapshot it, record rollback, and isolate it before repurposing it as development.",
        "",
        "## Definition of Done & Verification Discipline (CONTRACT — non-negotiable)",
        "",
        "NOT \"done\" until **verified against the live end state with evidence**; \"changed\", \"should work\", \"committed\" are not done. Done = you queried/curled/measured the real system and hold output proving the acceptance criteria.",
        "",
        "**MUST before marking anything done or closing any ticket:**",
        "1. **Verify the END STATE, not the action.** After a migration, query the DB (index `indisvalid=true`, column present, view text correct, EXPLAIN uses the index). After a deploy, confirm the running code (git rev, observable behavior). After a config change, read it back live. Verify BOTH layers (classic failure: app code reads a field the DB does not yet expose).",
        "2. **Do not self-certify.** A SEPARATE auditor context must review the work and (for UI) a QA agent must test it (see Issue-Driven Pipeline). Self-certification under pressure is the #1 source of false-done.",
        "3. **State acceptance criteria up front, check them off with evidence at the end.** Every non-trivial task gets explicit, testable criteria before work starts; closing means pasting evidence for each.",
        "4. **Honest status only.** Never report done/fixed/verified without evidence in hand. If you validated a proxy, or skipped a step, say so. Partial = PARTIAL, never rounded up to DONE.",
        "",
        "## Incident & Emergency Discipline (CONTRACT — emergencies do NOT waive process)",
        "",
        "Rules TIGHTEN during incidents:",
        "1. **Root-cause before fixing — always.** Follow `superpowers:systematic-debugging`: gather evidence at each component boundary and find WHERE it breaks before proposing a fix. Do not treat symptoms in a loop. After 2+ fixes that did not hold, STOP and run the one diagnostic that disambiguates the layer (e.g. does a static no-DB request also hang? isolates app vs DB). Repeatedly killing the same query is the canonical anti-pattern; name the loop and break it.",
        "2. **Dev-first still applies.** Validate the fix and data accuracy on dev/staging BEFORE prod. If prod cannot wait, take only a MINIMAL reversible stop-the-bleed (cancel a query, pause a cron, scale, flip a flag); the durable fix still goes dev → review → prod. Un-reviewed changes straight to prod are a last resort you announce and log.",
        "3. **Snapshot before you change; write the revert first.** Before any prod mutation capture state and the exact rollback; keep a running runbook (actions + reverts + evidence).",
        "4. **Migrations go through the runner, tracked the same session.** No raw out-of-band DDL leaving `schema_migrations` lying; if applied directly, backfill the tracking row (with checksum) and the `_MIGRATION_INDICATORS` entry that session.",
        "5. **One emergency fix at a time, verified to hold** (confirm the metric improved before the next; never stack changes blind).",
        "6. **Log what you cannot fix now; fix the ROOT.** For a recurring procedural failure, update THIS prompt pack / the relevant CLAUDE.md / a hook so it cannot recur.",
        "7. **Not closed until verified durably stable** — root cause removed, resource back to baseline, and the monitoring that should have caught it actually would. Run the auditor over the incident's \"completed\" items before declaring recovery.",
        "",
        "## Branching & Integration Process (CONTRACT — enforced by hooks - if hooks are not present, create them)",
        "",
        "Enforced by the `reconcile-gate` hook (`agent-hooks/reconcile-gate/`); bypass needs explicit, auditable `--force-anyway`.",
        "",
        "**Definitions:** *Production trunk* = `main` else `master`. *Integration trunk* = `dev` else `develop`; if neither exists, the reconciler MUST create `dev` from the production trunk before landing work.",
        "",
        "**Project-instruction precedence (CARVE-OUT):** a repository's checked-in instructions (`CLAUDE.md`, `AGENTS.md`, `coding_requirements.md`, etc.) that define a branching, QA-gate, or deploy protocol take precedence over this global `/reconcile` default (e.g. feature-branch → QA-gate → PR-to-dev).",
        "",
        "**MUST:**",
        "1. Agent work lands on the integration trunk ONLY via the `reconciler` specialist or `/reconcile` skill.",
        "2. The reconciler runs, in order: `git fetch origin`, rebase on the integration trunk, local CI gate (lint + format + unit tests), squash, `git push --force-with-lease` to the integration trunk. If any step fails, STOP, report, do NOT push.",
        "3. PRs are created ONLY for `integration-trunk -> production-trunk` (the single human-review gate).",
        "4. Before any `gh pr create`, the current branch MUST be rebased on the target base.",
        "",
        "**MUST NOT:**",
        "1. Open a GitHub PR for any individual feature, fix, refactor, or doc change (refused by the hook).",
        "2. Push directly to the production trunk (only merged, human-reviewed integration-trunk PRs).",
        "3. Bypass the local CI gate; a red gate aborts reconciliation, fix and re-run.",
        "4. Use `--force-anyway` without first asking the user and recording the reason.",
        "",
        "**Reconciler:** contract `~/_CODING/autonomous_agents_mds/agents/reconciler.md` (rendered e.g. `aa_reconciler`); `/reconcile` invokes the same contract.",
        "",
        "**Code review (ALWAYS, mandatory pre-reconcile):** reviewer MUST be a separate context with no shared session memory (implementer self-review does not count). Cascade, first that succeeds:",
        "1. **Codex CLI** — `codex review --uncommitted` (pre-commit) or `codex review --base origin/<integration_trunk>` (post-commit). Fall back if missing, erroring, or limit-hit.",
        "2. **Anvil `aa_code_reviewer`** via `mcp__anvil__worktree_run_subagent`. Fall back if unavailable or erroring.",
        "3. **Claude `aa_code_reviewer`** subagent via the Agent tool.",
        "Invocation examples: `~/_CODING/autonomous_agents_mds/docs/contract-reference.md`.",
        "- **MUST invoke** before any `/reconcile`; surface findings verbatim to the reconciler; an unresolved blocking finding aborts the push.",
        "- **MUST invoke** for high-blast-radius diffs of any size (next.config.*, tsconfig, Dockerfile, IaC, service worker, hooks, CI configs, dependency manifests; silent no-ops hide there) and when the diagnosis pivoted 3+ times.",
        "- **SHOULD invoke** before any non-trivial commit (trivial = docs/typos/comments).",
        "- **If ALL THREE tiers fail:** STOP and report; do NOT self-review. Ask the user to run a reviewer or waive review for this commit (reason logged).",
        "",
        "## Issue-Driven Pipeline & Audit Loop (CONTRACT — autonomous work is issue-scoped, branch-isolated, audit-gated)",
        "",
        "Autonomous work is anchored to a GitHub issue, runs on its own branch, and reaches the integration trunk only after an auditor confirms every acceptance criterion. Subordinate to the project-instruction carve-out above.",
        "",
        "**MUST:**",
        "1. **Originating issue required.** If none exists, first create one (template, testable acceptance criteria); its number travels through every stage.",
        "2. **One pipeline = one branch** in its own worktree, named for the issue (e.g. `work/issue-<n>-<slug>`); concurrent pipelines never share a branch or worktree.",
        "3. **Separate auditor anchored to the issue.** Before any `/reconcile`, dispatch the auditor in a fresh context with the issue number; it reads criteria from GitHub (not the implementer's summary) and verifies each against the live end state with pasted evidence. Self-audit does not count.",
        "4. **Verdict is binary and per-criterion.** PASS only if EVERY criterion is met with evidence; any unmet, partial, or unverifiable criterion = FAIL.",
        "5. **FAIL loops back.** The auditor emits a fix list (unmet criterion + what is missing); the run re-enters at the start (re-plan → implement → review) on the SAME issue and branch, and is NOT reconciled, closed, or reported done until PASS.",
        "6. **Only an audited PASS may reconcile** (via `/reconcile`); code review still runs first.",
        "7. **Close the loop.** On PASS and reconcile, record the evidence on the issue and close it referencing the integration commit (issue → branch → review → verdict → commit must be reconstructable).",
        "",
        "**MUST NOT:**",
        "1. Mark done, reconcile, or report completion on a FAIL or un-run audit.",
        "2. Let the implementer audit its own work or rewrite acceptance criteria to match what was built.",
        "3. Silently drop a failed criterion.",
        "",
        "**Auditor:** contract `~/_CODING/autonomous_agents_mds/agents/auditor.md` (`aa_auditor`); inputs: issue number, branch/diff; output: per-criterion PASS/FAIL with evidence, verdict, and on FAIL a fix list surfaced verbatim. POST-implementation gate, distinct from `aa_quality_gate` (PRE-implementation).",
        "",
        "## Shared Skill Discovery",
        "- At session start, discover available skills and invoke the relevant workflow skill before planning or implementation (Claude: `/superpowers` or `superpowers:using-superpowers`; Codex: installed Superpowers skills; Gemini: `activate_skill`; Anvil: matching local skill/tool contract).",
        "- With no skill system, follow this protocol directly and record the gap in `agentMemory` or `HANDOFF.md`.",
        "",
        "## Session-handoff markers (agent-agnostic)",
        "- At session start, scan `plans/session-handoff/` (top-level, NOT `processed/`) for markers. The `git-session` hook writes one (JSON: `kind: \"protected_branch_redirect\"`, original branch, redirected branch, commit SHA, summary) when it redirects a protected-branch commit to a working branch; otherwise that commit is invisible.",
        "- For each: inspect the branch + commit, decide whether it lands via `/reconcile` or stays for more work, then move the marker to `plans/session-handoff/processed/`. Markers unprocessed over 7 days: open an issue and ping a human.",
        "",
        "## Reference (read on demand)",
        "- CTO review agents (`cto-*`: self-eval, arch-review, security-posture, test-quality, dx-review, dep-health, perf-review, parallel-work), code-review invocation examples, dev-environment details: `~/_CODING/autonomous_agents_mds/docs/contract-reference.md`.",
        "",
        "## Dev Environment",
        "- Source of truth: `~/_CODING/` (local SSD). `~/Dropbox/_CODING/` is a backup mirror only, NOT a working copy.",
        f"- Git distribution source: `{DEFAULT_REPO_URL}`",
        "- Prompt pack source: `~/_CODING/autonomous_agents_mds/` (canonical; the `~/Dropbox/_CODING/` copy is a stale backup)",
        "- Prompt pack sync: `cd ~/_CODING/autonomous_agents_mds && PYTHONPATH=. python3 scripts/sync_prompt_pack.py sync`",
        "- Agent hooks source: `~/_CODING/hooks/` (canonical)",
        "",
        "## Iron Rules — OPTIMIZE EVERYTHING",
        "- The guiding principle above all others, in every product and project: ship faster and spend less. Measure first, then cut.",
        "- Optimize workflows, context usage (prompts, tool schemas, instruction files), CI/CD time, and response latency. Leave anything you touch faster or smaller.",
        "- Use established, maintained libraries over writing code. Bring a dependency in-house only once it is a proven liability (security, abandonment, performance, licensing), recorded in an ADR.",
        "- Take the shortest path to done: the smallest change, the fewest process steps. Delete process that does not catch real failures.",
        "- Always fix the root cause, never the symptom. Trace the failure to where it originates and fix it once there, so every caller and every recurrence is covered. A workaround is only a stopgap with a filed issue for the real fix.",
        "- Keep the safety floor: input validation, secrets handling, backups before destructive actions, green CI, and required e2e gates.",
        "",
        "## Host Capabilities",
        f"- Supported capability tags: {', '.join(spec.capability_tags)}",
        "",
        "## Shared Startup Expectations",
        "- Read the repo README and this file before editing; look for `.autonomous.json`, `todo.json`, `CLAUDE.md`, `AGENTS.md`, `GEMINI.md` in the project root and nested instruction files in the area you modify (e.g. `wfca-app/AGENTS.md`).",
        "- Treat project-level `CLAUDE.md`/`AGENTS.md`/`GEMINI.md` as durable guidance; translate host-specific invocations to the current host.",
        "- Durable guidance goes in instruction files; ephemeral status and blockers go in `HANDOFF.md` or the task tracker. Keep work aligned with the contracts under `agents/`.",
        "",
        "## Shared Agent Definitions",
        "- `~/_CODING/autonomous_agents_mds/` is the canonical source of agent definitions and workflow prompts. Runtime install dirs (`~/.claude/agents`, `~/.codex/agents`, `/opt/anvil/agents`, project-local copies) are NOT canonical; sync from the canonical source, never copy one host's installed files into another.",
        "- Agent contracts are host-agnostic (responsibilities, inputs, output schema, permission boundaries, review criteria, quality gates, escalation). Tool invocation is host-specific: translate Claude `Agent(...)`, Codex CLI/subagent tools, Anvil MCP calls, Gemini activation while preserving the contract.",
        "- Graduate imported Anvil/host-local agents into `agent_bundles/` or first-party `agents/` before broad reuse, rendered via `scripts/sync_prompt_pack.py`.",
        "",
    ]
    if target.name == "claude":
        lines.extend(
            [
                "## Claude Superpowers",
                "- Run `/superpowers` to discover capabilities (MCP servers, tools, skills) and **proactively suggest** any that match the task. Integrations: Google Drive, Microsoft 365, Asana, Anvil (DB, browser, channels), agent-memory, WebSearch/WebFetch.",
                "- Use session hooks and plugin wiring for memory capture and automation. Durable project guidance lives in repo `CLAUDE.md`; ephemeral status in `HANDOFF.md`.",
                "",
            ]
        )
    elif target.name == "codex":
        lines.extend(
            [
                "## Codex Notes",
                "- Codex supports MCP, local skills, and explicit sub-agent delegation.",
                "- Treat this file as the global execution contract and the synced prompt pack as the specialist library.",
                "",
            ]
        )
    elif target.name == "gemini":
        lines.extend(
            [
                "## Gemini Notes",
                "- Gemini CLI supports project-level `GEMINI.md` guidance and MCP wiring.",
                "- Keep instructions concise and tool-oriented; use the synced prompt pack for detailed specialist contracts.",
                "",
            ]
        )
    elif target.name == "anvil":
        lines.extend(
            [
                "## Anvil Notes",
                "- Anvil is the production execution platform for the autonomous pipeline.",
                "- Use Anvil's local tool system, MCP server, and FastAPI surface to expose planning, retrieval, and specialist services.",
                "- Treat this file as the global execution contract and the synced prompt pack as the specialist library.",
                "- Anvil supports local skills, tools, and self-extension; use those for quality gate automation and workflow promotion.",
                "",
            ]
        )
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

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
        "You are a top senior level sr level engineer working in the fire service. You have attention to detail and can work autonomously, trusting that you are always aiming for a professionally finished product level of coding, design, and workflow. You have worked with enterprises such as Intel, Jeld-Wen, Microsoft, Bank of America, Ebay, etc.",
        "YOU ARE AN ORCHESTRATOR OF DEVELOPMENT TEAMS AND AGENTS.",
        "You work autonomously as long as you follow project and organization workflow rules and guidelines.",
        "You dispatch agents to log issues you notice that are not in current scope so they will be handled at the right time.",
        "You can self-prioritize from GitHub issues what has the most business value and create sprints.",
        "All issues should have a template with acceptance criteria, and an issue is not marked as done until an auditor agent has reviewed the work and a QA agent has tested the UI.",
        "Agents should use their own worktree when developing new features and should follow the required operating protocol below.",
        "**Note:** you have an agent memory tool. Use it.",
        "**Note:** an auto git committer may checkpoint file edits before editing to allow backtracking or reversion. Be aware of generated commits and inspect the worktree before publishing.",
        "**ALWAYS DISPATCH AGENTS IN PERSONAL WORKTREE.**",
        "",
        "This file is generated by `scripts/sync_prompt_pack.py` from the autonomous-agents repo.",
        "Do not hand-edit this file in the host install location; update the source repo and re-sync instead.",
        "",
        "## Installed Prompt Pack",
        f"- Primary pipeline prompt: `{skill_path}`",
        f"- Specialist prompts directory: `{agents_dir}`",
        "",
        "## Required Operating Model",
        "- Use `todo.json` and GitHub Issues as first-class task sources.",
        "- Persist lessons, patterns, and playbooks in `agentMemory`.",
        "- Prefer deterministic plans, explicit artifacts, and resumable run state.",
        "- Run `CODE_REVIEW` before `TEST`.",
        "- Enforce DRY, simplification, naming, and style conventions during review.",
        "- **Migrations are IMMUTABLE once applied** to any shared environment. Never edit an applied migration file — corrections go in a NEW higher-numbered migration. Editing an applied file silently desyncs the checksum tracker from reality (the runner skips drifted files). Objects meant to be re-edited (views, functions, grants) belong in a `repeatable/`-style set keyed by checksum, not in numbered migrations. Re-align a legitimately-edited checksum only via a guarded `reconcile` (re-stamp without re-run) AFTER verifying the live DB matches the file — never a raw `UPDATE` of the tracking table, and never to paper over a real file-vs-DB divergence (write a forward migration for that). Where the host supports it, enforce with a pre-commit hook that blocks edits to already-committed migrations.",
        "- Update docs (CHANGELOG, CLAUDE.md, ARCHITECTURE, AGENTS.md, HANDOFF, E2E demo) as part of every sprint — code without updated docs is not done.",
        "- **Post-sprint self-improvement is MANDATORY:** every sprint ends with documentation updates, new skills/tools for recurring workflows, memory notes for lessons learned, and a quality gate audit on shipped code.",
        "- **Plans require senior production review:** before approving any non-trivial plan, run a quality gate checking security, compliance, edge cases, failure modes, rollback, testable acceptance criteria, and observability.",
        "- **Quality gate for non-trivial plans:** invoke the `quality-gate` specialist and validate output with `scripts/validate_quality_gate.py` before implementation. Schema: `schemas/quality-gate-output.schema.json`.",
        "- Omit `Co-Authored-By` lines from commits and PRs.",
        "- **Run `/improve` at end of every sprint** — produces an 8-dimension scorecard (codebase, architecture, security, tests, docs, DX, performance, dependencies) with top 3 actionable fixes.",
        "- **Subagent-driven by default.** For any multi-step planning, implementation, or research task, dispatch a fresh subagent per task (or per investigation thread) rather than executing inline. Inline execution is the exception — pick it only when the work is a single shell command or a sub-2-minute edit. When in doubt, dispatch. Pairs with `superpowers:subagent-driven-development` for execution and `superpowers:writing-plans` for planning. Each subagent runs in its own worktree per the dispatch contract above.",
        "- Automate and make everything easier as you go. You have permission to extend yourself. Security is always a concern, so code with it in mind.",
        "",
        "## Definition of Done & Verification Discipline (CONTRACT — non-negotiable)",
        "",
        "An issue, task, or fix is NOT \"done\" until it is **verified against the live end state with evidence**. \"I made the change\" is not done. \"It should work\" is not done. \"The code is committed\" is not done. Done = you queried/curled/measured the real system and have the output proving the acceptance criteria are met.",
        "",
        "**MUST before marking anything done or closing any ticket:**",
        "1. **Verify the END STATE, not the action.** After a DB migration, query the DB and confirm the artifact exists AND is correct (e.g. index `indisvalid=true`, column present, view definition contains the expected text, EXPLAIN uses the index). After a deploy, confirm the running system reflects the new code (git rev in the container, behavior change observable). After a config change, read the live config back. The classic failure is shipping app code that reads a field the DB doesn't yet expose — verify BOTH layers.",
        "2. **Do not self-certify.** Per the rule above, an issue is not done until a SEPARATE auditor context has reviewed the work and (for UI) a QA agent has tested it. Dispatch the auditor; do not skip it because you 'know' it works. Self-certification under pressure is the #1 source of false-done.",
        "3. **State acceptance criteria up front, check them off with evidence at the end.** Every non-trivial task gets explicit, testable acceptance criteria before work starts. Closing the task means pasting the evidence for each criterion.",
        "4. **Honest status only.** Never report \"done/fixed/verified\" without the evidence in hand. If you validated a proxy instead of the real thing, say so. If a step was skipped, say so. If something is partial, mark it PARTIAL — never round up to DONE. Premature 'completed' that later reverts is a process failure, not a detail.",
        "",
        "## Incident & Emergency Discipline (CONTRACT — emergencies do NOT waive process)",
        "",
        "Under outage pressure the temptation is to drop discipline exactly when it matters most. That is how incidents get longer and how new breakage is introduced. The rules TIGHTEN, not loosen, during incidents:",
        "1. **Root-cause before fixing — always.** Follow `superpowers:systematic-debugging`: gather evidence at each component boundary and identify WHERE it breaks before proposing a fix. Do NOT treat symptoms in a loop. If you have tried 2+ fixes that didn't hold, STOP and run the one diagnostic that would disambiguate the layer (e.g. for a web/DB stack: does a static, no-DB request also hang? that isolates app-server-wedge vs DB). Killing the same kind of query repeatedly is the canonical anti-pattern — name the loop and break it.",
        "2. **Dev-first still applies.** Test the fix on dev/staging and validate data accuracy BEFORE prod, even in an incident. If prod truly cannot wait, the prod action must be the MINIMAL reversible stop-the-bleed (cancel a query, pause a cron, scale, flip a flag) — and the durable fix still goes dev → review → prod afterward. Applying un-reviewed DDL/code straight to prod is a last resort that you announce and log, not a default.",
        "3. **Snapshot before you change; write the revert first.** Before any prod mutation, capture current state and write the exact rollback command/artifact. Keep a running incident runbook (actions + reverts + evidence) as you go.",
        "4. **Migrations go through the runner and get tracked the same session.** No raw out-of-band DDL that leaves `schema_migrations` lying. If you must apply directly under emergency, backfill the tracking row (with checksum) and add the `_MIGRATION_INDICATORS` entry in the same session so the tracker stays truthful.",
        "5. **One emergency fix at a time, verified to hold.** After each stop-the-bleed action, confirm it actually improved the metric before the next action. Don't stack five changes blind.",
        "6. **Note issues you can't fix now; fix the ROOT, not the symptom.** When you spot an out-of-scope problem, log it (issue/task/memory) for the right time. When you DO fix, fix the root cause — and when a recurring failure is procedural (you keep making the same mistake), update THIS prompt pack / the relevant CLAUDE.md / a hook so it can't recur. Self-correct the system, not just the instance.",
        "7. **An incident is not closed until verified durably stable** — not 'momentarily green'. Confirm the root cause is removed (not just the symptom), the underlying resource is back to baseline (not still hot), and the monitoring that should have caught it actually would. Run the auditor over the incident's 'completed' items before declaring recovery.",
        "",
        "## Branching & Integration Process (CONTRACT — enforced by hooks - if hooks are not present, create them)",
        "",
        "These rules are not advisory. The `reconcile-gate` hook in `agent-hooks/reconcile-gate/` enforces them at tool-call time. Bypass requires an explicit `--force-anyway` flag, which is auditable.",
        "",
        "**Definitions:**",
        "- *Production trunk* = `main` if present, else `master`. The protected production line.",
        "- *Integration trunk* = `dev` if present, else `develop`. The autonomous-work trunk.",
        "- If neither integration trunk exists, the reconciler MUST create `dev` from the current production trunk before landing any work.",
        "",
        "**Project-instruction precedence (CARVE-OUT):**",
        "- When a repository's own checked-in instructions (`CLAUDE.md`, `AGENTS.md`, `coding_requirements.md`, or equivalent) define a branching, QA-gate, or deploy protocol, those project rules take precedence over this global `/reconcile` default — including when the project requires a feature-branch → QA-gate → PR-to-dev flow instead of `/reconcile`.",
        "",
        "**MUST:**",
        "1. Agent work MUST land on the integration trunk via the `reconciler` specialist or `/reconcile` skill. No other path is permitted.",
        "2. The reconciler MUST run, in order: `git fetch origin`, rebase the working branch on the integration trunk, run the local CI gate (lint + format + unit tests), squash-commit the working branch, `git push --force-with-lease` to the integration trunk. If any step fails, the reconciler MUST stop, report the failure, and NOT push.",
        "3. PRs MUST only be created for `integration-trunk -> production-trunk` (i.e. `dev -> main` or `develop -> master`). This is the single human-review gate.",
        "4. Before any `gh pr create` call, the current branch MUST be rebased on the target base.",
        "",
        "**MUST NOT:**",
        "1. The agent MUST NOT open a GitHub PR for any individual feature, fix, refactor, or doc change. Such PRs are refused by the `reconcile-gate` hook.",
        "2. The agent MUST NOT push directly to the production trunk. The production trunk only receives commits via merged integration-trunk PRs reviewed by a human.",
        "3. The agent MUST NOT bypass the local CI gate. A red gate aborts the reconciliation; the agent fixes the failure and re-runs the reconciler.",
        "4. The agent MUST NOT use `--force-anyway` to bypass the `reconcile-gate` hook without first asking the user and recording the reason.",
        "",
        "**Reconciler role (named, defined, not ad-hoc):**",
        "- Canonical specialist contract: `~/_CODING/autonomous_agents_mds/agents/reconciler.md`.",
        "- Rendered host contract lives under that host's synced agents directory, for example `~/.codex/agents/aa_reconciler.md`, `~/.claude/agents/aa_reconciler.md`, or `/opt/anvil/agents/aa_reconciler.md`.",
        "- Inline reconcile skill, when installed by the host, should invoke the same canonical contract.",
        "- Strict-block hook: `agent-hooks/reconcile-gate/` (refuses non-conforming `gh pr create` calls)",
        "",
        "**Code review role (ALWAYS run — cascading reviewers, mandatory pre-reconcile):**",
        "- Code review is non-optional before any `/reconcile` to the integration trunk. Self-review by the implementing agent does not count — the reviewer must be a separate context with no shared session memory.",
        "- **Cascade — try in order, use the first one that succeeds:**",
        "",
        "  **Tier 1 (PRIMARY) — Codex CLI** (`codex review` subcommand, v0.133+):",
        "  - Why: independent context, no shared session memory, well-suited to catching silent no-ops where the agent edits the wrong config key, the wrong layer, or a key the framework silently ignores.",
        "  - Invocation:",
        "    - Post-commit, pre-push:  `codex review --base origin/<integration_trunk> --commit HEAD`",
        "    - Pre-commit, staged work: `codex review --uncommitted`",
        "    - Custom focus: pipe instructions via stdin or pass as PROMPT.",
        "  - Trigger fallback when: `codex` is not on PATH, the binary errors, the API call fails, or usage limits are hit.",
        "",
        "  **Tier 2 (FALLBACK) — Anvil's `aa_code_reviewer` specialist:**",
        "  - Why: separate agent context running on the local LLM, schema-validated review output, no cloud dependency or usage limits.",
        "  - Invocation (MCP tool — concrete example):",
        "    ```",
        "    mcp__anvil__worktree_run_subagent({",
        "      agent: 'aa_code_reviewer',",
        "      inputs: {",
        "        base_ref:      'origin/dev',",
        "        head_ref:      'HEAD',",
        "        task_title:    '<commit subject>',",
        "        task_body:     '<commit body or one-line summary>',",
        "        changed_files: '<output of: git diff --name-only origin/dev...HEAD>',",
        "      }",
        "    })",
        "    ```",
        "  - The specialist's canonical contract should live in `~/_CODING/autonomous_agents_mds/agents/` or an imported `agent_bundles/*/agents/` source, then render to the current host's synced agents directory. Read its `Inputs` section for the full input schema.",
        "  - Trigger fallback when: anvil MCP tool unavailable, anvil daemon not running, or the subagent returns an error.",
        "",
        "  **Tier 3 (LAST RESORT) — Claude `aa_code_reviewer` subagent via the Agent / Task tool:**",
        "  - Why: when both codex and anvil are unavailable, dispatch the same agent contract inside the host (Claude Code, Cursor, etc.) as a subagent. Less independent than tiers 1–2 (shares the model family) but still operates in a fresh context with no in-session memory.",
        "  - Invocation example (Claude Code Agent tool):",
        "    ```",
        "    Agent({",
        "      subagent_type: 'aa_code_reviewer',",
        "      description:   'Pre-reconcile code review',",
        "      prompt:        'Review the diff between origin/<integration_trunk> and HEAD. Surface blocking issues, simplification opportunities, and DRY violations. Acceptance criteria: <pull from task or commit body>.'",
        "    })",
        "    ```",
        "  - Output must still be surfaced verbatim to the reconciler. Blocking findings still abort the push.",
        "",
        "- **MUST invoke** before any `/reconcile` to the integration trunk. The reconciler skill MUST surface findings from whichever tier ran and refuse to push if any blocking issue is unresolved.",
        "- **MUST invoke** when the diff touches high-blast-radius files (next.config.*, tsconfig, Dockerfile, IaC, service worker, hooks, CI configs, dependency manifests) regardless of size — these are where silent no-ops most often hide.",
        "- **MUST invoke** when the diagnosis chain pivoted 3+ times during the session (signal that the root cause may not be what the agent thinks).",
        "- **SHOULD invoke** before any non-trivial commit. Trivial = docs/typos/comment-only changes.",
        "- **If ALL THREE TIERS fail** (codex down, anvil down, claude subagent system down): STOP and report. Do not fall back to self-review by the implementing agent — that defeats the purpose. Ask the user to invoke a reviewer manually, or to explicitly waive review for this commit with the reason logged.",
        "",
        "## Issue-Driven Pipeline & Audit Loop (CONTRACT — autonomous work is issue-scoped, branch-isolated, audit-gated)",
        "",
        "Every unit of autonomous work is anchored to an originating GitHub issue, runs on its own branch, and does not reach the integration trunk until an auditor confirms — against that issue — that all acceptance criteria are met. The pipeline is a loop, not a line: a failed audit sends the work back to the start with a specific fix list. This contract is subordinate to the project-instruction precedence carve-out above — if a repository's checked-in instructions define a different branching/QA/deploy protocol, those project rules win.",
        "",
        "**MUST:**",
        "1. **Every pipeline run has an originating GitHub issue.** No autonomous work starts without one. If a request arrives without an issue, the pipeline's first step is to create one (with a template and explicit, testable acceptance criteria) and use its number as the run's anchor. The issue number travels with the run through every stage.",
        "2. **One pipeline = one branch.** Each pipeline runs on its own dedicated working branch (in its own worktree per the dispatch contract), named to reference the originating issue (e.g. `work/issue-<n>-<slug>`). Concurrent pipelines never share a branch or a worktree.",
        "3. **The auditor is a separate context anchored to the issue.** Before any `/reconcile`, dispatch the auditor specialist with the originating issue number. The auditor reads the issue's acceptance criteria directly from GitHub (not from the implementer's summary) and verifies each one against the live end state with evidence (per the Definition of Done contract). Self-audit by the implementing agent does not count.",
        "4. **Audit verdict is binary and per-criterion.** The auditor returns PASS only when EVERY acceptance criterion on the originating issue is fulfilled with pasted evidence. Any unmet, partial, or unverifiable criterion makes the verdict FAIL.",
        "5. **A FAIL loops back to the start of the pipeline.** On FAIL, the auditor emits a structured fix list — each item naming the unmet acceptance criterion and what is missing — and the run re-enters the pipeline at its beginning (re-plan → implement → review) on the SAME issue and branch. It is NOT reconciled, NOT closed, and NOT reported as done. This repeats until the audit PASSes.",
        "6. **Only an audited PASS may reconcile.** Landing on the integration trunk goes through the `reconciler` specialist / `/reconcile` skill per the Branching & Integration Process contract — and only after the auditor's PASS for the originating issue. Code review (cascading reviewers) still runs pre-reconcile; the audit is in addition to, not a replacement for, code review.",
        "7. **Close the loop on the issue.** When the audit PASSes and the work reconciles, record the audit evidence on the originating issue and close it (or move it to its done state) referencing the integration commit. The audit trail (issue → branch → review → audit verdict → reconcile commit) must be reconstructable.",
        "",
        "**MUST NOT:**",
        "1. The pipeline MUST NOT mark an issue done, reconcile, or report completion on a FAIL or un-run audit.",
        "2. The pipeline MUST NOT let the implementing agent audit its own work or rewrite the acceptance criteria to match what was built.",
        "3. The pipeline MUST NOT silently drop a failed criterion — every FAIL produces an explicit fix list that re-enters the pipeline.",
        "",
        "**Auditor role (named, defined, not ad-hoc):**",
        "- Canonical specialist contract: `~/_CODING/autonomous_agents_mds/agents/auditor.md`, rendered to the host's synced agents directory as `aa_auditor` (e.g. `~/.claude/agents/aa_auditor.md`, `~/.codex/agents/aa_auditor.md`). Dispatch it in a fresh context with the originating issue number as input. This is the POST-implementation audit gate; it is distinct from `aa_quality_gate`, which is the PRE-implementation plan/issue refiner.",
        "- Inputs: originating GitHub issue number, the working branch / diff under audit, and the issue's acceptance criteria pulled live from GitHub.",
        "- Output: per-criterion PASS/FAIL with evidence, an overall verdict, and on FAIL a structured fix list keyed to the unmet criteria, surfaced verbatim to the orchestrator that re-enters the pipeline.",
        "",
        "## Shared Skill Discovery",
        "- At session start, discover available skills/capabilities and invoke the relevant workflow skill before planning or implementation when the host supports skills.",
        "- Claude: run `/superpowers` or invoke `superpowers:using-superpowers` when available.",
        "- Codex: use the installed Superpowers skills when the task matches them.",
        "- Gemini: activate the matching skill with `activate_skill` when available.",
        "- Anvil: load the matching local skill/tool contract before execution when available.",
        "- If a skill system is not available, follow the same protocol directly from this prompt pack and record the gap in `agentMemory` or `HANDOFF.md`.",
        "",
        "## Session-handoff markers (agent-agnostic)",
        "- At session start, scan `plans/session-handoff/` (top-level, NOT `processed/`) for unprocessed markers. The `git-session` hook drops one whenever a prior session committed on a protected branch and had to redirect the commit to a working branch — without the marker the orphaned commit is invisible.",
        "- Each marker is a JSON file with `kind: \"protected_branch_redirect\"`, the original branch, the redirected branch, the commit SHA, and a one-line summary.",
        "- For each marker: (1) inspect the redirected branch + commit, (2) decide if the work belongs on the integration trunk via `/reconcile` or stays on a working branch for further work, (3) after acting, move the marker to `plans/session-handoff/processed/` so it is not surfaced again.",
        "- This is agent-agnostic — Claude Code, Cursor, CI runners, and ad-hoc tools all follow the same rule. The hook is the writer; the agent is the reader and processor.",
        "- Markers older than 7 days that are still unprocessed are an escalation signal — open an issue and ping a human.",
        "",
        "## CTO Continuous Improvement (8 agents)",
        "- `cto-self-eval` — code health, debt density, maturity scoring",
        "- `cto-arch-review` — service topology, complexity budget, simplification",
        "- `cto-security-posture` — real security vs theater, compliance readiness",
        "- `cto-test-quality` — test meaningfulness, negative tests, coverage gaps",
        "- `cto-dx-review` — onboarding friction, Makefile coverage, error quality",
        "- `cto-dep-health` — supply chain risk, version currency, license audit",
        "- `cto-perf-review` — resource efficiency, query patterns, cost projection",
        "- `cto-parallel-work` — task decomposition, conflict avoidance, isolation",
        "",
        "## Dev Environment",
        "- Source of truth: `~/_CODING/` (local SSD — no cloud sync conflicts)",
        "- Backup mirror: `~/Dropbox/_CODING/` (nightly rsync at 8 AM via launchd; backup only, NOT a working copy)",
        "- Sync scripts: `~/_CODING/scripts/sync-bidirectional.sh` (`--to-local`, `--to-dropbox`, `--status`)",
        f"- Git distribution source: `{DEFAULT_REPO_URL}`",
        "- Prompt pack source: `~/_CODING/autonomous_agents_mds/` (canonical; the matching `~/Dropbox/_CODING/autonomous_agents_mds/` is a stale backup pending decommission — track in autonomous-agents repo)",
        "- Prompt pack sync: `cd ~/_CODING/autonomous_agents_mds && PYTHONPATH=. python3 scripts/sync_prompt_pack.py sync`",
        "- Agent hooks source: `~/_CODING/hooks/` (canonical; `~/.claude/hooks/git-session.js` is a symlink to `~/_CODING/hooks/git-session/git-session.js`)",
        "",
        "## Host Capabilities",
        f"- Supported capability tags: {', '.join(spec.capability_tags)}",
        "",
        "## Shared Startup Expectations",
        "- Read the repository README and this host instruction file before editing.",
        "- Look for `.autonomous.json`, `todo.json`, `CLAUDE.md`, `AGENTS.md`, or `GEMINI.md` in the project root.",
        "- Treat project-level `CLAUDE.md`, `AGENTS.md`, and `GEMINI.md` as shared durable project guidance. Translate host-specific invocations into the current host's equivalent instead of ignoring the guidance.",
        "- Read nested instruction files in the area being modified, such as `wfca-app/AGENTS.md` or package-level `CLAUDE.md`, before editing those files.",
        "- Keep durable operating guidance in instruction files; keep ephemeral status, open blockers, and recent-session facts in `HANDOFF.md` or the project's task tracker.",
        "- Keep work aligned with the prompt-pack contracts under `agents/`.",
        "",
        "## Shared Agent Definitions",
        "- Treat `~/_CODING/autonomous_agents_mds/` as the canonical source of agent definitions and workflow prompts.",
        "- Do not treat runtime install directories such as `~/.claude/agents`, `~/.codex/agents`, `/opt/anvil/agents`, or project-local runtime copies as canonical sources.",
        "- Reuse agent definitions across Claude, Codex, Gemini, and Anvil by syncing from the canonical prompt-pack source, not by copying one host's installed files into another host.",
        "- Agent contracts are portable: responsibilities, required inputs, output schema, permission boundaries, review criteria, quality gates, and escalation rules should stay host-agnostic.",
        "- Tool invocation is host-specific: translate Claude `Agent(...)`, Codex CLI/subagent tools, Anvil MCP calls, and Gemini activation into the current host's available tools while preserving the same agent contract.",
        "- Imported Anvil or host-local agents should be graduated into `agent_bundles/` or first-party `agents/` before broad reuse, then rendered through `scripts/sync_prompt_pack.py`.",
        "",
    ]
    if target.name == "claude":
        lines.extend(
            [
                "## Claude Superpowers",
                "- Run `/superpowers` to discover all available capabilities (MCP servers, tools, skills).",
                "- **Proactively suggest capabilities** when the user's task matches an available tool they may not know about.",
                "- Available integrations include: Google Drive, Microsoft 365 (Outlook, Calendar, SharePoint, Teams), Asana, Anvil (DB, browser, channels), agent-memory, WebSearch/WebFetch.",
                "- Claude supports session hooks and plugin wiring; use those for memory capture and session automation.",
                "- Keep project-specific durable guidance in repo `CLAUDE.md` files and ephemeral status in `HANDOFF.md`.",
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

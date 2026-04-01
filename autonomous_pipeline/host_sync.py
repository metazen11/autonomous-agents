from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path


HOST_NAMES = ("claude", "codex", "gemini", "cursor", "openclaw")


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
}


@dataclass(slots=True)
class HostTarget:
    name: str
    skill_path: Path | None = None
    agents_dir: Path | None = None
    instructions_path: Path | None = None
    config_snippet_path: Path | None = None

    @property
    def configured(self) -> bool:
        return any(
            value is not None
            for value in (self.skill_path, self.agents_dir, self.instructions_path, self.config_snippet_path)
        )


@dataclass(slots=True)
class SyncStatus:
    host: str
    configured: bool
    skill_in_sync: bool | None = None
    instructions_in_sync: bool | None = None
    config_snippet_in_sync: bool | None = None
    missing_agents: list[str] | None = None


def repo_skill_source(repo_root: Path) -> Path:
    return repo_root / "pipeline" / "autonomous.md"


def repo_agent_sources(repo_root: Path) -> list[Path]:
    return sorted((repo_root / "agents").glob("*.md"))


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
        target = HostTarget(
            name=host,
            skill_path=Path(skill_path) if skill_path else None,
            agents_dir=Path(agents_dir) if agents_dir else None,
            instructions_path=Path(instructions_path) if instructions_path else None,
            config_snippet_path=Path(config_snippet_path) if config_snippet_path else None,
        )
        if not target.configured:
            continue
        targets.append(target)
    return targets


def sync_target(repo_root: Path, target: HostTarget) -> None:
    if target.skill_path and target.agents_dir:
        target.skill_path.parent.mkdir(parents=True, exist_ok=True)
        target.agents_dir.mkdir(parents=True, exist_ok=True)

        target.skill_path.write_text(repo_skill_source(repo_root).read_text())
        source_names = {source.name for source in repo_agent_sources(repo_root)}
        for target_file in target.agents_dir.glob("*.md"):
            if target_file.name not in source_names:
                target_file.unlink()
        for source in repo_agent_sources(repo_root):
            (target.agents_dir / source.name).write_text(source.read_text())

    if target.instructions_path:
        target.instructions_path.parent.mkdir(parents=True, exist_ok=True)
        target.instructions_path.write_text(render_host_instructions(repo_root, target))

    if target.config_snippet_path:
        snippet = render_host_config_snippet(repo_root, target)
        if snippet:
            target.config_snippet_path.parent.mkdir(parents=True, exist_ok=True)
            target.config_snippet_path.write_text(snippet)


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
                target_file = target.agents_dir / source.name
                if not target_file.exists() or sha256_file(source) != sha256_file(target_file):
                    missing_agents.append(source.name)

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

    return SyncStatus(
        host=target.name,
        configured=True,
        skill_in_sync=skill_in_sync,
        instructions_in_sync=instructions_in_sync,
        config_snippet_in_sync=config_snippet_in_sync,
        missing_agents=missing_agents,
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def host_capabilities() -> dict[str, tuple[str, ...]]:
    return {name: spec.capability_tags for name, spec in HOST_SPECS.items()}


def render_host_instructions(repo_root: Path, target: HostTarget) -> str:
    spec = HOST_SPECS[target.name]
    skill_path = target.skill_path or repo_root / "pipeline" / "autonomous.md"
    agents_dir = target.agents_dir or repo_root / "agents"
    lines = [
        f"# {spec.instruction_filename}",
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
        "",
        "## Host Capabilities",
        f"- Supported capability tags: {', '.join(spec.capability_tags)}",
        "",
        "## Shared Startup Expectations",
        "- Read the repository README and this host instruction file before editing.",
        "- Look for `.autonomous.json`, `todo.json`, `CLAUDE.md`, `AGENTS.md`, or `GEMINI.md` in the project root.",
        "- Keep work aligned with the prompt-pack contracts under `agents/`.",
        "",
    ]
    if target.name == "claude":
        lines.extend(
            [
                "## Claude Notes",
                "- Claude supports session hooks and plugin wiring well; use those for memory capture and session automation.",
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
            f'            "command": "cd {repo_root} && python3 scripts/sync_prompt_pack.py sync --repo-root {repo_root}",\n'
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
    return f"*/15 * * * * cd {shell_escape(str(repo_root))} && {shell_escape(python_bin)} {shell_escape(str(script))} sync >/dev/null 2>&1"


def anacron_line(repo_root: Path, python_bin: str = "python3") -> str:
    script = repo_root / "scripts" / "sync_prompt_pack.py"
    return f"15 10 autonomous-prompt-pack cd {shell_escape(str(repo_root))} && {shell_escape(python_bin)} {shell_escape(str(script))} sync >/dev/null 2>&1"


def windows_task_command(repo_root: Path, python_bin: str = "python") -> str:
    script = repo_root / "scripts" / "sync_prompt_pack.py"
    return f'{python_bin} "{script}" sync --repo-root "{repo_root}"'


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
    arguments = f'"{script}" sync --repo-root "{repo_root}"'
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


def install_git_hooks(repo_root: Path, python_bin: str = "python3") -> list[Path]:
    hooks_dir = repo_root / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    script = repo_root / "scripts" / "sync_prompt_pack.py"
    body = (
        "#!/usr/bin/env sh\n"
        "# Auto-generated by scripts/sync_prompt_pack.py\n"
        f"cd {shell_escape(str(repo_root))} || exit 0\n"
        f"{shell_escape(python_bin)} {shell_escape(str(script))} sync --repo-root {shell_escape(str(repo_root))} >/dev/null 2>&1 || true\n"
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

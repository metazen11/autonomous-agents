from __future__ import annotations


def extract_checklist(body: str) -> list[str]:
    """Extract unchecked checklist items (lines starting with '- [ ] ') from a body."""
    lines = []
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if line.startswith("- [ ] "):
            lines.append(line[6:])
    return lines

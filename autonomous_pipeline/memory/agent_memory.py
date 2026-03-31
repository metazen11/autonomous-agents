from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


class AgentMemoryError(RuntimeError):
    """Raised when the remote agent-memory service call fails."""


@dataclass(slots=True)
class AgentMemoryClient:
    base_url: str = "http://127.0.0.1:3377"
    timeout_seconds: float = 5.0

    def get_health(self) -> dict[str, Any]:
        try:
            return self._request("GET", "/api/health")
        except AgentMemoryError:
            # Backward-compatible fallback for older deployments.
            return self._request("GET", "/health")

    def health(self) -> bool:
        try:
            data = self.get_health()
            return data.get("status") in {"ok", "degraded"}
        except AgentMemoryError:
            return False

    def search_observations(self, query: str, project: str, limit: int = 5) -> dict[str, Any]:
        payload = {
            "query": query,
            "project": project,
            "limit": limit,
            "mode": "hybrid",
            "cross_project": False,
        }
        return self._request("POST", "/api/observations/search", payload)

    def create_lesson(
        self,
        *,
        rule: str,
        title: str,
        project: str | None = None,
        severity: str = "warning",
        trigger_tool: str | None = None,
        trigger_pattern: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "project": project,
            "title": title,
            "rule": rule,
            "severity": severity,
            "trigger_tool": trigger_tool,
            "trigger_pattern": trigger_pattern,
            "source_observation_id": None,
        }
        return self._request("POST", "/api/lessons", payload)

    def list_lessons(self, project: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        query = urllib.parse.urlencode({"project": project or "", "limit": str(limit)})
        path = f"/api/lessons?{query}"
        data = self._request("GET", path)
        if not isinstance(data, list):
            raise AgentMemoryError("Unexpected response from /api/lessons")
        return data

    def match_lessons(self, *, tool_name: str, tool_input_preview: str = "", project: str | None = None) -> list[dict[str, Any]]:
        query = urllib.parse.urlencode(
            {
                "tool_name": tool_name,
                "tool_input_preview": tool_input_preview,
                "project": project or "",
            }
        )
        data = self._request("GET", f"/api/lessons/match?{query}")
        if not isinstance(data, list):
            raise AgentMemoryError("Unexpected response from /api/lessons/match")
        return data

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url.rstrip('/')}{path}"
        body = None
        headers = {}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise AgentMemoryError(f"{method} {path} failed: {exc.code} {detail}") from exc
        except urllib.error.URLError as exc:
            raise AgentMemoryError(f"{method} {path} failed: {exc.reason}") from exc

        if not raw:
            return {}
        return json.loads(raw)

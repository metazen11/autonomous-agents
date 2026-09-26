from __future__ import annotations

import os
import unittest
import unittest.mock

from autonomous_pipeline.adapters.asana import AsanaAdapter
from autonomous_pipeline.adapters.base import TaskAdapterError
from autonomous_pipeline.schemas import TaskUpdate


class FakeHttp:
    """Records requests, returns queued responses."""

    def __init__(self, responses: list[dict]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, str, dict]] = []

    def __call__(self, method: str, url: str, headers: dict, body: bytes | None) -> dict:
        self.calls.append((method, url, headers))
        return self.responses.pop(0)


class AsanaAdapterReadTest(unittest.TestCase):
    def test_list_ready_tasks_normalizes_incomplete(self) -> None:
        http = FakeHttp(
            [
                {
                    "data": [
                        {"gid": "111", "name": "Fix centroid", "notes": "do it", "completed": False},
                        {"gid": "222", "name": "Done thing", "notes": "", "completed": True},
                    ]
                }
            ]
        )
        adapter = AsanaAdapter(project_gid="proj1", token="fake", http=http)
        tasks = adapter.list_ready_tasks()
        self.assertEqual([t.id for t in tasks], ["111"])
        task = tasks[0]
        self.assertEqual(task.title, "Fix centroid")
        self.assertEqual(task.source, "asana")
        self.assertEqual(task.metadata["tracker_ref"], "111")
        self.assertIn("111", task.source_url)

    def test_list_ready_tasks_sends_bearer_token(self) -> None:
        http = FakeHttp([{"data": []}])
        adapter = AsanaAdapter(project_gid="proj1", token="secret-token", http=http)
        adapter.list_ready_tasks()
        _, url, headers = http.calls[0]
        self.assertIn("proj1", url)
        self.assertEqual(headers["Authorization"], "Bearer secret-token")

    def test_get_task_extracts_acceptance_criteria(self) -> None:
        http = FakeHttp(
            [
                {
                    "data": {
                        "gid": "333",
                        "name": "Task with criteria",
                        "notes": "Intro\n- [ ] first crit\n- [ ] second crit",
                        "completed": False,
                    }
                }
            ]
        )
        adapter = AsanaAdapter(project_gid="proj1", token="fake", http=http)
        task = adapter.get_task("333")
        self.assertEqual(task.acceptance_criteria, ["first crit", "second crit"])


class AsanaAdapterTokenTest(unittest.TestCase):
    def test_missing_token_raises(self) -> None:
        def fake_http(method, url, headers, body):
            raise AssertionError("http transport should not be called")

        with unittest.mock.patch.dict(os.environ, {}, clear=True):
            adapter = AsanaAdapter(project_gid="p1", token=None, http=fake_http)
            with self.assertRaises(TaskAdapterError):
                adapter.list_ready_tasks()

    def test_token_read_from_env(self) -> None:
        received_headers: list[dict] = []

        def fake_http(method, url, headers, body):
            received_headers.append(dict(headers))
            return {"data": []}

        with unittest.mock.patch.dict(os.environ, {"ASANA_ACCESS_TOKEN": "env-token"}, clear=True):
            adapter = AsanaAdapter(project_gid="p1", http=fake_http)
            adapter.list_ready_tasks()

        self.assertEqual(received_headers[0]["Authorization"], "Bearer env-token")


class AsanaAdapterWriteTest(unittest.TestCase):
    def test_update_task_marks_completed_when_done(self) -> None:
        http = FakeHttp(
            [
                {"data": {"gid": "444"}},  # story comment POST
                {"data": {"gid": "444"}},  # completed PUT
                {"data": {"gid": "444", "name": "T", "notes": "", "completed": True}},  # re-fetch
            ]
        )
        adapter = AsanaAdapter(project_gid="proj1", token="fake", http=http)
        task = adapter.update_task("444", TaskUpdate(status="done", append_phase_log="audited PASS"))
        self.assertEqual(task.status, "done")
        methods = [call[0] for call in http.calls]
        self.assertIn("PUT", methods)

    def test_update_task_does_not_mark_completed_when_not_done(self) -> None:
        http = FakeHttp(
            [
                {"data": {"gid": "777"}},  # story comment POST
                {"data": {"gid": "777", "name": "T", "notes": "", "completed": False}},  # re-fetch
            ]
        )
        adapter = AsanaAdapter(project_gid="proj1", token="fake", http=http)
        adapter.update_task("777", TaskUpdate(status="in_progress"))
        methods = [call[0] for call in http.calls]
        self.assertNotIn("PUT", methods)

    def test_create_item_returns_gid_and_url(self) -> None:
        http = FakeHttp([{"data": {"gid": "555"}}])
        adapter = AsanaAdapter(project_gid="proj1", token="fake", http=http)
        gid, url = adapter.create_item(
            title="New captured task",
            body="intent",
            criteria=["crit one", "crit two"],
            labels=["lane:etl"],
        )
        self.assertEqual(gid, "555")
        self.assertIn("555", url)
        # last call is the create POST to /tasks
        method, called_url, _ = http.calls[-1]
        self.assertEqual(method, "POST")
        self.assertTrue(called_url.endswith("/tasks"))


if __name__ == "__main__":
    unittest.main()

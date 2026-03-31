from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from autonomous_pipeline.adapters.github import GitHubAdapter


class GitHubAdapterNormalizationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.script_path = Path(self.tmpdir.name) / "fake_gh.py"
        self.script_path.write_text(
            "\n".join(
                [
                    "#!/usr/bin/env python3",
                    "import json, sys",
                    "args = sys.argv[1:]",
                    "if args[:3] == ['issue', 'list', '--state']:",
                    "    print(json.dumps([",
                    "        {'number': 12, 'title': 'High priority issue', 'body': '- [ ] add tests', 'labels': [{'name': 'priority:high'}], 'url': 'https://example/12'},",
                    "        {'number': 15, 'title': 'Blocked issue', 'body': '', 'labels': [{'name': 'blocked'}], 'url': 'https://example/15'}",
                    "    ]))",
                    "elif args[:2] == ['issue', 'view']:",
                    "    issue_id = args[2]",
                    "    print(json.dumps({'number': int(issue_id), 'title': f'Issue {issue_id}', 'body': '- [ ] verify', 'labels': [{'name': 'priority:urgent'}], 'url': f'https://example/{issue_id}'}))",
                    "elif args[:2] == ['issue', 'comment']:",
                    "    print('')",
                    "elif args[:2] == ['issue', 'create']:",
                    "    print(json.dumps({'number': 99, 'url': 'https://example/99'}))",
                    "else:",
                    "    raise SystemExit('unsupported args: ' + ' '.join(args))",
                ]
            )
            + "\n"
        )
        self.script_path.chmod(0o755)
        self.adapter = GitHubAdapter(
            repo_root=self.tmpdir.name,
            gh_command=["python3", str(self.script_path)],
        )

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_list_ready_tasks_filters_skip_labels_and_maps_priority(self) -> None:
        tasks = self.adapter.list_ready_tasks()
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].id, "12")
        self.assertEqual(tasks[0].priority, "high")
        self.assertEqual(tasks[0].acceptance_criteria, ["add tests"])

    def test_get_task_maps_issue(self) -> None:
        task = self.adapter.get_task("42")
        self.assertEqual(task.id, "42")
        self.assertEqual(task.priority, "urgent")
        self.assertEqual(task.acceptance_criteria, ["verify"])

    def test_create_follow_up_returns_issue_number(self) -> None:
        issue_id = self.adapter.create_follow_up(
            item=type(
                "Candidate",
                (),
                {
                    "title": "Promote repeated checks",
                    "description": "Automate a stable command chain",
                    "expected_benefit": "fewer manual commands",
                    "source_evidence": ["run-1", "run-2"],
                },
            )()
        )
        self.assertEqual(issue_id, "99")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from docdb.adk.roadmap import RoadmapDocument, RoadmapTask, load_roadmap, save_roadmap, select_next_task, set_task_status


class RoadmapTests(unittest.TestCase):
    def test_save_and_load_round_trip(self) -> None:
        document = RoadmapDocument(
            title="Test Roadmap",
            tasks=[
                RoadmapTask(
                    id="task-1",
                    title="First",
                    action="refresh_doc_index",
                    success_criteria=["A"],
                    verification=["B"],
                )
            ],
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "roadmap.md"
            save_roadmap(path, document)
            loaded = load_roadmap(path)

        self.assertEqual(loaded.title, "Test Roadmap")
        self.assertEqual(loaded.tasks[0].id, "task-1")
        self.assertEqual(loaded.tasks[0].action, "refresh_doc_index")

    def test_select_next_task_skips_blocked_dependencies(self) -> None:
        document = RoadmapDocument(
            title="Test",
            tasks=[
                RoadmapTask(id="task-1", title="First", status="done"),
                RoadmapTask(id="task-2", title="Second", depends_on=["task-1"]),
                RoadmapTask(id="task-3", title="Third", depends_on=["task-2"]),
            ],
        )

        next_task = select_next_task(document)
        self.assertIsNotNone(next_task)
        self.assertEqual(next_task.id, "task-2")

        set_task_status(document, "task-2", "done")
        self.assertEqual(select_next_task(document).id, "task-3")

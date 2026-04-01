from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from docdb.adk.actions import ActionResult
from docdb.adk.roadmap import RoadmapDocument, RoadmapTask, save_roadmap
from docdb.adk.workflow import LocalWorkflowEngine


class WorkflowTests(unittest.TestCase):
    def test_run_next_marks_task_done_when_verification_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            roadmap_path = base_dir / "docs" / "adk-roadmap.md"
            history_path = base_dir / "data" / "runs.json"
            save_roadmap(
                roadmap_path,
                RoadmapDocument(
                    title="Workflow",
                    tasks=[
                        RoadmapTask(
                            id="task-1",
                            title="Run",
                            action="refresh_doc_index",
                        )
                    ],
                ),
            )
            engine = LocalWorkflowEngine(
                repo_name="cursorai",
                base_dir=base_dir,
                roadmap_path=roadmap_path,
                history_path=history_path,
            )

            with (
                patch(
                    "docdb.adk.workflow.execute_action",
                    return_value=ActionResult(
                        action="refresh_doc_index",
                        ok=True,
                        summary="done",
                    ),
                ),
                patch(
                    "docdb.adk.workflow.verify_action",
                    return_value=(True, ["verified"]),
                ),
            ):
                payload = engine.run_next()

            self.assertEqual(payload["status"], "done")
            self.assertEqual(payload["verifier"]["notes"], ["verified"])
            self.assertTrue(history_path.exists())

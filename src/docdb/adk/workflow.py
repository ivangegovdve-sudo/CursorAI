from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .actions import ActionResult, execute_action, verify_action
from .roadmap import load_roadmap, select_next_task, set_task_status


@dataclass(slots=True)
class RunRecord:
    repo: str
    task_id: str
    task_title: str
    status: str
    started_at: str
    finished_at: str
    adapter: str
    summary: str
    executor: dict[str, Any]
    verifier: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class NoOpOrchestrationAdapter:
    name = "noop"

    def prepare_task(self, task: Any) -> dict[str, Any]:
        return {
            "adapter": self.name,
            "task_id": task.id,
            "task_title": task.title,
        }


class LocalWorkflowEngine:
    def __init__(
        self,
        *,
        repo_name: str,
        base_dir: Path,
        roadmap_path: Path,
        history_path: Path,
        adapter: NoOpOrchestrationAdapter | None = None,
    ) -> None:
        self.repo_name = repo_name
        self.base_dir = base_dir
        self.roadmap_path = roadmap_path
        self.history_path = history_path
        self.adapter = adapter or NoOpOrchestrationAdapter()
        self.history_path.parent.mkdir(parents=True, exist_ok=True)

    def roadmap_snapshot(self) -> dict[str, Any]:
        return load_roadmap(self.roadmap_path).to_dict()

    def run_next(self) -> dict[str, Any]:
        document = load_roadmap(self.roadmap_path)
        task = select_next_task(document)
        if task is None:
            return {
                "repo": self.repo_name,
                "status": "idle",
                "reason": "No unblocked roadmap tasks remain.",
                "roadmap": document.to_dict(),
            }

        started_at = _utc_now()
        set_task_status(document, task.id, "running")
        from .roadmap import save_roadmap  # local import to keep import graph simple

        save_roadmap(self.roadmap_path, document)

        adapter_result = self.adapter.prepare_task(task)
        try:
            executor_result = execute_action(task.action, self.base_dir, task.arguments)
            verified, verification_notes = verify_action(
                task.action,
                self.base_dir,
                task.arguments,
                executor_result,
            )
            if not verified:
                repaired = execute_action(task.action, self.base_dir, task.arguments)
                repaired.repaired = True
                repaired_ok, repaired_notes = verify_action(
                    task.action,
                    self.base_dir,
                    task.arguments,
                    repaired,
                )
                verified = repaired_ok
                verification_notes = [*verification_notes, *repaired_notes]
                if repaired_ok:
                    executor_result = repaired

            executor_result.verification_notes = verification_notes
            final_status = "done" if verified else "blocked"
            verifier_result = {
                "ok": verified,
                "notes": verification_notes,
                "repaired": executor_result.repaired,
            }
            summary = executor_result.summary
        except Exception as exc:  # noqa: BLE001
            final_status = "blocked"
            summary = f"Task failed: {exc}"
            executor_result = ActionResult(
                action=task.action,
                ok=False,
                summary=summary,
                details={"error": str(exc)},
            )
            verifier_result = {
                "ok": False,
                "notes": [str(exc)],
                "repaired": False,
            }

        finished_at = _utc_now()
        set_task_status(document, task.id, final_status)
        save_roadmap(self.roadmap_path, document)

        record = RunRecord(
            repo=self.repo_name,
            task_id=task.id,
            task_title=task.title,
            status=final_status,
            started_at=started_at,
            finished_at=finished_at,
            adapter=adapter_result["adapter"],
            summary=summary,
            executor=executor_result.to_dict(),
            verifier=verifier_result,
        )
        self._append_history(record)

        return {
            "repo": self.repo_name,
            "status": final_status,
            "task": task.to_dict(),
            "adapter": adapter_result,
            "summary": summary,
            "executor": executor_result.to_dict(),
            "verifier": verifier_result,
            "roadmap": document.to_dict(),
            "record": record.to_dict(),
        }

    def load_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        if not self.history_path.exists():
            return []
        payload = json.loads(self.history_path.read_text(encoding="utf-8"))
        return list(reversed(payload.get("runs", [])[-limit:]))

    def _append_history(self, record: RunRecord) -> None:
        payload = {"runs": []}
        if self.history_path.exists():
            payload = json.loads(self.history_path.read_text(encoding="utf-8"))
        payload.setdefault("runs", []).append(record.to_dict())
        self.history_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

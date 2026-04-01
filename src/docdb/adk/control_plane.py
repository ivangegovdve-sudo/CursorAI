from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import threading
from typing import Any

from .roadmap import load_roadmap
from .workflow import LocalWorkflowEngine, NoOpOrchestrationAdapter


@dataclass(slots=True)
class RepoTarget:
    key: str
    label: str
    kind: str
    base_dir: Path
    roadmap_path: Path
    runner: LocalWorkflowEngine | None = None


class ControlPlaneService:
    def __init__(self, workspace_root: Path, cursorai_root: Path) -> None:
        self.workspace_root = workspace_root
        self.cursorai_root = cursorai_root
        self._lock = threading.Lock()
        self._scheduler_thread: threading.Thread | None = None
        self._scheduler_stop = threading.Event()
        self._scheduler_interval_seconds = 300
        self._active_run: dict[str, Any] | None = None
        self._control_history_path = self.cursorai_root / "data" / "adk_control_plane_runs.json"
        self._control_history_path.parent.mkdir(parents=True, exist_ok=True)

        local_runner = LocalWorkflowEngine(
            repo_name="cursorai",
            base_dir=self.cursorai_root,
            roadmap_path=self.cursorai_root / "docs" / "adk-roadmap.md",
            history_path=self.cursorai_root / "data" / "adk_local_runs.json",
            adapter=NoOpOrchestrationAdapter(),
        )
        python_learning_root = workspace_root / "python-learning-orchestrated"
        self.targets: dict[str, RepoTarget] = {
            "cursorai": RepoTarget(
                key="cursorai",
                label="CursorAI",
                kind="local",
                base_dir=self.cursorai_root,
                roadmap_path=self.cursorai_root / "docs" / "adk-roadmap.md",
                runner=local_runner,
            ),
            "python-learning-orchestrated": RepoTarget(
                key="python-learning-orchestrated",
                label="Python Learning Orchestrated",
                kind="subprocess",
                base_dir=python_learning_root,
                roadmap_path=python_learning_root / "docs" / "adk-roadmap.md",
            ),
        }

    def status_snapshot(self) -> dict[str, Any]:
        return {
            "active_run": self._active_run,
            "repos": {
                key: self.roadmap_snapshot(key)
                for key in self.targets
            },
            "scheduler": {
                "interval_seconds": self._scheduler_interval_seconds,
                "running": self._scheduler_thread is not None and self._scheduler_thread.is_alive(),
            },
        }

    def roadmap_snapshot(self, repo: str) -> dict[str, Any]:
        document = load_roadmap(self.targets[repo].roadmap_path)
        return {
            "repo": repo,
            "roadmap": document.to_dict(),
        }

    def run_next(self, repo: str) -> dict[str, Any]:
        targets = list(self.targets.values()) if repo == "all" else [self.targets[repo]]
        run_id = _utc_now()
        if not self._lock.acquire(blocking=False):
            return {
                "status": "busy",
                "message": "A control-plane run is already in progress.",
                "active_run": self._active_run,
            }

        self._active_run = {
            "repo": repo,
            "run_id": run_id,
            "started_at": _utc_now(),
        }
        try:
            results = [self._run_target(target) for target in targets]
            status = "completed"
            if any(result.get("status") == "blocked" for result in results):
                status = "completed_with_issues"
            payload = {
                "run_id": run_id,
                "repo": repo,
                "started_at": self._active_run["started_at"],
                "finished_at": _utc_now(),
                "status": status,
                "results": results,
            }
            self._append_control_history(payload)
            return payload
        finally:
            self._active_run = None
            self._lock.release()

    def load_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        if not self._control_history_path.exists():
            return []
        payload = json.loads(self._control_history_path.read_text(encoding="utf-8"))
        return list(reversed(payload.get("runs", [])[-limit:]))

    def start_scheduler(self, interval_seconds: int = 300) -> dict[str, Any]:
        self._scheduler_interval_seconds = max(interval_seconds, 30)
        if self._scheduler_thread and self._scheduler_thread.is_alive():
            return {
                "running": True,
                "interval_seconds": self._scheduler_interval_seconds,
            }

        self._scheduler_stop.clear()
        self._scheduler_thread = threading.Thread(
            target=self._scheduler_loop,
            name="cursorai-adk-scheduler",
            daemon=True,
        )
        self._scheduler_thread.start()
        return {
            "running": True,
            "interval_seconds": self._scheduler_interval_seconds,
        }

    def stop_scheduler(self) -> dict[str, Any]:
        self._scheduler_stop.set()
        if self._scheduler_thread and self._scheduler_thread.is_alive():
            self._scheduler_thread.join(timeout=2)
        return {"running": False}

    def _scheduler_loop(self) -> None:
        while not self._scheduler_stop.wait(self._scheduler_interval_seconds):
            self.run_next("all")

    def _run_target(self, target: RepoTarget) -> dict[str, Any]:
        if target.kind == "local" and target.runner is not None:
            return target.runner.run_next()
        return self._run_python_learning_target(target)

    def _run_python_learning_target(self, target: RepoTarget) -> dict[str, Any]:
        python_path = target.base_dir / ".venv" / "Scripts" / "python.exe"
        command = [
            str(python_path),
            "-m",
            "python_learning_orchestrated",
            "adk-run-next",
            "--json",
            "--progress-file",
            "data/adk-progress.json",
            "--roadmap-file",
            "docs/adk-roadmap.md",
            "--session-file",
            "data/adk-session.json",
        ]
        env = os.environ.copy()
        env["PYTHONPATH"] = "src"
        completed = subprocess.run(
            command,
            cwd=target.base_dir,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        if completed.returncode != 0:
            return {
                "repo": target.key,
                "status": "blocked",
                "summary": completed.stderr.strip() or completed.stdout.strip(),
            }
        return json.loads(completed.stdout)

    def _append_control_history(self, record: dict[str, Any]) -> None:
        payload = {"runs": []}
        if self._control_history_path.exists():
            payload = json.loads(self._control_history_path.read_text(encoding="utf-8"))
        payload.setdefault("runs", []).append(record)
        self._control_history_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def create_control_plane_service() -> ControlPlaneService:
    cursorai_root = Path(__file__).resolve().parents[3]
    workspace_root = cursorai_root.parent
    return ControlPlaneService(workspace_root=workspace_root, cursorai_root=cursorai_root)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

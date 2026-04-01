from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import re
from typing import Any

VALID_STATUSES = {"todo", "running", "done", "blocked"}
TASK_HEADING_RE = re.compile(r"^###\s+`(?P<task_id>[^`]+)`\s+-\s+(?P<title>.+)$")


@dataclass(slots=True)
class RoadmapTask:
    id: str
    title: str
    status: str = "todo"
    depends_on: list[str] = field(default_factory=list)
    action: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    success_criteria: list[str] = field(default_factory=list)
    verification: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RoadmapDocument:
    title: str
    tasks: list[RoadmapTask] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "tasks": [task.to_dict() for task in self.tasks],
        }


def load_roadmap(path: str | Path) -> RoadmapDocument:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    title = "ADK Roadmap"
    tasks: list[RoadmapTask] = []
    current: RoadmapTask | None = None
    section: str | None = None

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("# "):
            title = stripped[2:].strip()
            continue

        heading_match = TASK_HEADING_RE.match(stripped)
        if heading_match:
            if current is not None:
                tasks.append(current)
            current = RoadmapTask(
                id=heading_match.group("task_id"),
                title=heading_match.group("title"),
            )
            section = None
            continue

        if current is None:
            continue

        if stripped.startswith("Status:"):
            current.status = _normalize_status(stripped.partition(":")[2].strip())
            section = None
            continue
        if stripped.startswith("Depends on:"):
            dependency_text = stripped.partition(":")[2].strip()
            current.depends_on = [] if dependency_text in {"", "none"} else [
                item.strip() for item in dependency_text.split(",") if item.strip()
            ]
            section = None
            continue
        if stripped.startswith("Action:"):
            current.action = stripped.partition(":")[2].strip()
            section = None
            continue
        if stripped.startswith("Arguments:"):
            payload = stripped.partition(":")[2].strip()
            current.arguments = json.loads(payload) if payload else {}
            section = None
            continue
        if stripped == "Success criteria:":
            section = "success"
            continue
        if stripped == "Verification:":
            section = "verification"
            continue
        if stripped.startswith("- ") and section == "success":
            current.success_criteria.append(stripped[2:].strip())
            continue
        if stripped.startswith("- ") and section == "verification":
            current.verification.append(stripped[2:].strip())
            continue

    if current is not None:
        tasks.append(current)

    return RoadmapDocument(title=title, tasks=tasks)


def save_roadmap(path: str | Path, document: RoadmapDocument) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# {document.title}", ""]
    for task in document.tasks:
        depends_on = ", ".join(task.depends_on) if task.depends_on else "none"
        lines.append(f"### `{task.id}` - {task.title}")
        lines.append(f"Status: {_normalize_status(task.status)}")
        lines.append(f"Depends on: {depends_on}")
        lines.append(f"Action: {task.action}")
        lines.append(
            "Arguments: "
            + json.dumps(task.arguments, sort_keys=True, separators=(",", ":"))
        )
        lines.append("Success criteria:")
        for item in task.success_criteria:
            lines.append(f"- {item}")
        lines.append("Verification:")
        for item in task.verification:
            lines.append(f"- {item}")
        lines.append("")
    target.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def set_task_status(
    document: RoadmapDocument,
    task_id: str,
    status: str,
) -> RoadmapTask:
    normalized = _normalize_status(status)
    for task in document.tasks:
        if task.id == task_id:
            task.status = normalized
            return task
    raise KeyError(f"Unknown roadmap task: {task_id}")


def select_next_task(document: RoadmapDocument) -> RoadmapTask | None:
    completed = {task.id for task in document.tasks if task.status == "done"}
    for task in document.tasks:
        if task.status != "todo":
            continue
        if all(dep in completed for dep in task.depends_on):
            return task
    return None


def _normalize_status(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in VALID_STATUSES:
        raise ValueError(f"Unsupported roadmap status: {value}")
    return normalized

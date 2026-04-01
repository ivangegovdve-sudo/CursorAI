from __future__ import annotations

import os

from google.adk import Agent
from google.adk.apps import App
from google.adk.plugins import LoggingPlugin, ReflectAndRetryToolPlugin

from .control_plane import create_control_plane_service


def build_app() -> App:
    service = create_control_plane_service()
    model_name = os.environ.get("ADK_MODEL", "gemini-2.5-flash")

    def list_cursorai_roadmap() -> dict:
        """Return the current CursorAI roadmap and task statuses."""
        return service.roadmap_snapshot("cursorai")

    def list_learning_roadmap() -> dict:
        """Return the current python-learning roadmap and task statuses."""
        return service.roadmap_snapshot("python-learning-orchestrated")

    def run_next_cursorai_task() -> dict:
        """Execute the next eligible CursorAI roadmap task and verify it."""
        return service.run_next("cursorai")

    def run_next_learning_task() -> dict:
        """Execute the next eligible python-learning roadmap task and verify it."""
        return service.run_next("python-learning-orchestrated")

    def list_recent_runs() -> dict:
        """Return recent control-plane run history."""
        return {"runs": service.load_runs()}

    executor_agent = Agent(
        name="executor",
        model=model_name,
        description="Executes the next roadmap task for one of the managed repos.",
        instruction=(
            "Execute one roadmap task at a time. Prefer repo-specific run tools over "
            "describing the work abstractly."
        ),
        tools=[
            list_cursorai_roadmap,
            list_learning_roadmap,
            run_next_cursorai_task,
            run_next_learning_task,
        ],
    )

    verifier_agent = Agent(
        name="verifier_fixer",
        model=model_name,
        description="Verifies task outcomes and reviews run history.",
        instruction=(
            "Review the latest run results, confirm whether verification passed, and "
            "suggest a follow-up only when a task is blocked."
        ),
        tools=[list_recent_runs, list_cursorai_roadmap, list_learning_roadmap],
    )

    root_agent = Agent(
        name="cursorai_orchestrator",
        model=model_name,
        description="Coordinates CursorAI and python-learning roadmap execution.",
        instruction=(
            "Coordinate the executor and verifier_fixer agents. Use the roadmap tools "
            "to decide which repository should advance next."
        ),
        sub_agents=[executor_agent, verifier_agent],
        tools=[list_recent_runs],
    )

    return App(
        name="cursorai_adk_control_plane",
        root_agent=root_agent,
        plugins=[LoggingPlugin(), ReflectAndRetryToolPlugin(max_retries=2)],
    )

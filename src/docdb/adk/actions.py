from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any, Callable
from urllib.request import Request, urlopen

from docdb.parser import parse_llms_text, records_from_docs
from docdb.storage import (
    build_context,
    connect_db,
    export_platform_csvs,
    finish_ingest_run,
    init_db,
    list_platforms,
    load_platforms,
    query_documents,
    replace_platform_documents,
    start_ingest_run,
    upsert_platforms,
)


USER_AGENT = "CursorAI-ADK/0.1"
ARTIFACTS_DIR = Path("data") / "adk_artifacts"


@dataclass(slots=True)
class ActionResult:
    action: str
    ok: bool
    summary: str
    artifacts: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    verification_notes: list[str] = field(default_factory=list)
    repaired: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


ActionFn = Callable[[Path, dict[str, Any]], ActionResult]
ValidatorFn = Callable[[Path, dict[str, Any], ActionResult], tuple[bool, list[str]]]


def execute_action(action_name: str, base_dir: Path, arguments: dict[str, Any]) -> ActionResult:
    return ACTIONS[action_name](base_dir, arguments)


def verify_action(
    action_name: str,
    base_dir: Path,
    arguments: dict[str, Any],
    result: ActionResult,
) -> tuple[bool, list[str]]:
    return VALIDATORS[action_name](base_dir, arguments, result)


def refresh_doc_index(base_dir: Path, arguments: dict[str, Any]) -> ActionResult:
    db_path = base_dir / arguments.get("db_path", "data/doc_pages.db")
    platforms_path = base_dir / arguments.get("platforms_path", "config/platforms.json")
    export_dir = base_dir / arguments.get("export_dir", "data/spreadsheets")
    platforms = load_platforms(platforms_path)

    conn = connect_db(db_path)
    init_db(conn)
    upsert_platforms(conn, platforms)
    run_id = start_ingest_run(conn)
    doc_counts: dict[str, int] = {}
    exported_files: list[Path] = []

    try:
        for platform in platforms:
            text = _fetch_text(platform["llms_url"])
            docs = parse_llms_text(
                text,
                source_url=platform["llms_url"],
                platform_id=platform["id"],
            )
            records = records_from_docs(docs)
            replace_platform_documents(conn, platform["id"], records)
            doc_counts[platform["id"]] = len(records)
        finish_ingest_run(conn, run_id, status="completed")
        exported_files = export_platform_csvs(conn, export_dir)
        return ActionResult(
            action="refresh_doc_index",
            ok=True,
            summary=f"Indexed {sum(doc_counts.values())} documents across {len(doc_counts)} platforms.",
            artifacts=[str(path.relative_to(base_dir)) for path in exported_files],
            details={
                "db_path": str(db_path.relative_to(base_dir)),
                "doc_counts": doc_counts,
                "platform_count": len(doc_counts),
            },
        )
    finally:
        conn.close()


def export_platform_summary(base_dir: Path, arguments: dict[str, Any]) -> ActionResult:
    db_path = base_dir / arguments.get("db_path", "data/doc_pages.db")
    output_name = arguments.get("output_name", "platform-summary.json")
    artifact_path = _artifact_path(base_dir, output_name)

    conn = connect_db(db_path)
    try:
        platforms = [dict(row) for row in list_platforms(conn)]
    finally:
        conn.close()

    payload = {"platforms": platforms}
    artifact_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return ActionResult(
        action="export_platform_summary",
        ok=True,
        summary=f"Wrote platform summary for {len(platforms)} platforms.",
        artifacts=[str(artifact_path.relative_to(base_dir))],
        details={"platform_count": len(platforms)},
    )


def build_context_snapshot(base_dir: Path, arguments: dict[str, Any]) -> ActionResult:
    db_path = base_dir / arguments.get("db_path", "data/doc_pages.db")
    output_name = arguments.get("output_name", "context-snapshot.txt")
    artifact_path = _artifact_path(base_dir, output_name)

    conn = connect_db(db_path)
    try:
        rows = query_documents(
            conn,
            platform=arguments.get("platform"),
            section=arguments.get("section"),
            search=arguments.get("search"),
            markdown_only=bool(arguments.get("markdown_only", False)),
            limit=int(arguments.get("limit", 20)),
        )
    finally:
        conn.close()

    context = build_context(rows, question=arguments.get("question"))
    artifact_path.write_text(context, encoding="utf-8")
    return ActionResult(
        action="build_context_snapshot",
        ok=True,
        summary=f"Built a context snapshot from {len(rows)} indexed documents.",
        artifacts=[str(artifact_path.relative_to(base_dir))],
        details={"document_count": len(rows)},
    )


def validate_refresh_doc_index(
    base_dir: Path,
    arguments: dict[str, Any],
    result: ActionResult,
) -> tuple[bool, list[str]]:
    db_path = base_dir / arguments.get("db_path", "data/doc_pages.db")
    export_dir = base_dir / arguments.get("export_dir", "data/spreadsheets")
    if not db_path.exists():
        return False, [f"Database file does not exist at {db_path}."]

    conn = connect_db(db_path)
    try:
        platforms = [dict(row) for row in list_platforms(conn)]
    finally:
        conn.close()
    if not platforms:
        return False, ["No platforms were indexed."]
    if sum(int(platform.get("doc_count") or 0) for platform in platforms) <= 0:
        return False, ["Indexed platform counts are empty."]

    csv_files = list(export_dir.glob("*.csv"))
    if not csv_files:
        return False, ["CSV exports were not generated."]
    return True, [f"Verified {len(platforms)} indexed platforms and {len(csv_files)} CSV exports."]


def validate_export_platform_summary(
    base_dir: Path,
    arguments: dict[str, Any],
    result: ActionResult,
) -> tuple[bool, list[str]]:
    artifact_path = _artifact_path(base_dir, arguments.get("output_name", "platform-summary.json"))
    if not artifact_path.exists():
        return False, [f"Summary artifact missing: {artifact_path}"]
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    platforms = payload.get("platforms", [])
    if not platforms:
        return False, ["Summary artifact does not contain any platforms."]
    return True, [f"Verified platform summary for {len(platforms)} platforms."]


def validate_build_context_snapshot(
    base_dir: Path,
    arguments: dict[str, Any],
    result: ActionResult,
) -> tuple[bool, list[str]]:
    artifact_path = _artifact_path(base_dir, arguments.get("output_name", "context-snapshot.txt"))
    if not artifact_path.exists():
        return False, [f"Context artifact missing: {artifact_path}"]
    content = artifact_path.read_text(encoding="utf-8")
    if "Documentation index context:" not in content:
        return False, ["Context artifact does not contain the expected heading."]
    return True, [f"Verified context snapshot at {artifact_path.name}."]


def _fetch_text(url: str, timeout: int = 30) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def _artifact_path(base_dir: Path, output_name: str) -> Path:
    target = base_dir / ARTIFACTS_DIR / output_name
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


ACTIONS: dict[str, ActionFn] = {
    "refresh_doc_index": refresh_doc_index,
    "export_platform_summary": export_platform_summary,
    "build_context_snapshot": build_context_snapshot,
}

VALIDATORS: dict[str, ValidatorFn] = {
    "refresh_doc_index": validate_refresh_doc_index,
    "export_platform_summary": validate_export_platform_summary,
    "build_context_snapshot": validate_build_context_snapshot,
}

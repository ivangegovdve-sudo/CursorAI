from __future__ import annotations

import csv
import json
from pathlib import Path
import sqlite3
from typing import Iterable


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS platforms (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    llms_url TEXT NOT NULL,
    homepage TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS ingest_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT,
    status TEXT NOT NULL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform_id TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    rel_path TEXT NOT NULL,
    section TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    content_type TEXT NOT NULL,
    is_markdown INTEGER NOT NULL DEFAULT 0,
    line_no INTEGER,
    source_url TEXT NOT NULL,
    inserted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(platform_id, url),
    FOREIGN KEY(platform_id) REFERENCES platforms(id)
);

CREATE INDEX IF NOT EXISTS idx_documents_platform_id ON documents(platform_id);
CREATE INDEX IF NOT EXISTS idx_documents_section ON documents(section);
CREATE INDEX IF NOT EXISTS idx_documents_markdown ON documents(is_markdown);
"""


def connect_db(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def load_platforms(path: str | Path) -> list[dict[str, str]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data.get("platforms", [])


def upsert_platforms(conn: sqlite3.Connection, platforms: Iterable[dict[str, str]]) -> None:
    conn.executemany(
        """
        INSERT INTO platforms (id, name, llms_url, homepage, notes)
        VALUES (:id, :name, :llms_url, :homepage, :notes)
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            llms_url = excluded.llms_url,
            homepage = excluded.homepage,
            notes = excluded.notes
        """,
        [
            {
                "id": platform["id"],
                "name": platform["name"],
                "llms_url": platform["llms_url"],
                "homepage": platform.get("homepage"),
                "notes": platform.get("notes"),
            }
            for platform in platforms
        ],
    )
    conn.commit()


def start_ingest_run(conn: sqlite3.Connection, status: str = "running", notes: str = "") -> int:
    cur = conn.execute(
        "INSERT INTO ingest_runs (status, notes) VALUES (?, ?)",
        (status, notes),
    )
    conn.commit()
    return int(cur.lastrowid)


def finish_ingest_run(conn: sqlite3.Connection, run_id: int, status: str, notes: str = "") -> None:
    conn.execute(
        "UPDATE ingest_runs SET finished_at = CURRENT_TIMESTAMP, status = ?, notes = ? WHERE id = ?",
        (status, notes, run_id),
    )
    conn.commit()


def replace_platform_documents(
    conn: sqlite3.Connection,
    platform_id: str,
    records: Iterable[dict[str, object]],
) -> None:
    conn.execute("DELETE FROM documents WHERE platform_id = ?", (platform_id,))
    conn.executemany(
        """
        INSERT INTO documents (
            platform_id, title, url, rel_path, section, description, content_type,
            is_markdown, line_no, source_url
        )
        VALUES (
            :platform_id, :title, :url, :rel_path, :section, :description, :content_type,
            :is_markdown, :line_no, :source_url
        )
        """,
        [
            {
                **record,
                "is_markdown": 1 if record.get("is_markdown") else 0,
            }
            for record in records
        ],
    )
    conn.commit()


def query_documents(
    conn: sqlite3.Connection,
    *,
    platform: str | None = None,
    section: str | None = None,
    search: str | None = None,
    markdown_only: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> list[sqlite3.Row]:
    clauses: list[str] = []
    params: list[object] = []

    if platform:
        clauses.append("platform_id = ?")
        params.append(platform)
    if section:
        clauses.append("section = ?")
        params.append(section)
    if markdown_only:
        clauses.append("is_markdown = 1")
    if search:
        clauses.append("(title LIKE ? OR description LIKE ? OR url LIKE ? OR rel_path LIKE ?)")
        pattern = f"%{search}%"
        params.extend([pattern, pattern, pattern, pattern])

    where_sql = ""
    if clauses:
        where_sql = "WHERE " + " AND ".join(clauses)

    sql = f"""
        SELECT platform_id, title, url, rel_path, section, description, content_type, is_markdown
        FROM documents
        {where_sql}
        ORDER BY platform_id, section, title
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])
    return list(conn.execute(sql, params))


def list_platforms(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    sql = """
        SELECT
            p.id,
            p.name,
            p.llms_url,
            p.homepage,
            COUNT(d.id) AS doc_count,
            SUM(CASE WHEN d.is_markdown = 1 THEN 1 ELSE 0 END) AS markdown_count
        FROM platforms p
        LEFT JOIN documents d ON p.id = d.platform_id
        GROUP BY p.id, p.name, p.llms_url, p.homepage
        ORDER BY p.name
    """
    return list(conn.execute(sql))


def list_sections(conn: sqlite3.Connection, platform: str | None = None) -> list[str]:
    if platform:
        rows = conn.execute(
            "SELECT DISTINCT section FROM documents WHERE platform_id = ? ORDER BY section",
            (platform,),
        )
    else:
        rows = conn.execute("SELECT DISTINCT section FROM documents ORDER BY section")
    return [row[0] for row in rows]


def export_platform_csvs(
    conn: sqlite3.Connection,
    out_dir: str | Path,
    *,
    markdown_only: bool = False,
) -> list[Path]:
    output_dir = Path(out_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    files: list[Path] = []
    platforms = list_platforms(conn)
    for platform in platforms:
        rows = query_documents(
            conn,
            platform=platform["id"],
            markdown_only=markdown_only,
            limit=100000,
        )
        path = output_dir / f"{platform['id']}.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "platform_id",
                    "title",
                    "url",
                    "rel_path",
                    "section",
                    "description",
                    "content_type",
                    "is_markdown",
                ],
            )
            writer.writeheader()
            for row in rows:
                writer.writerow(dict(row))
        files.append(path)
    return files


def export_records_csv(path: str | Path, records: Iterable[dict[str, object]]) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "platform_id",
                "title",
                "url",
                "rel_path",
                "section",
                "description",
                "content_type",
                "is_markdown",
                "line_no",
                "source_url",
            ],
        )
        writer.writeheader()
        for record in records:
            writer.writerow(record)
    return output_path


def build_context(rows: Iterable[sqlite3.Row | dict[str, object]], question: str | None = None) -> str:
    lines: list[str] = []
    if question:
        lines.append(f"Question: {question}")
        lines.append("")
    lines.append("Documentation index context:")
    for row in rows:
        item = dict(row)
        description = item.get("description") or ""
        description_text = f" - {description}" if description else ""
        lines.append(
            f"- [{item['platform_id']}] {item['title']} ({item['section']}) -> {item['url']}{description_text}"
        )
    return "\n".join(lines)

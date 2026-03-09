from __future__ import annotations

import argparse
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from pathlib import Path
import sys

from .openai_client import OpenAIClientError, ask_openai
from .parser import parse_llms_text, records_from_docs
from .server import serve
from .storage import (
    build_context,
    connect_db,
    export_platform_csvs,
    export_records_csv,
    finish_ingest_run,
    init_db,
    load_platforms,
    query_documents,
    replace_platform_documents,
    start_ingest_run,
    upsert_platforms,
)


USER_AGENT = "CursorAI-DocDB/0.1"


def fetch_text(url: str, timeout: int = 30) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def fetch_and_parse_platform(platform: dict[str, str], timeout: int = 30) -> list[dict[str, object]]:
    text = fetch_text(platform["llms_url"], timeout=timeout)
    docs = parse_llms_text(text, source_url=platform["llms_url"], platform_id=platform["id"])
    return records_from_docs(docs)


def print_rows(rows: list[dict[str, object]]) -> None:
    for row in rows:
        description = row.get("description") or ""
        suffix = f" | {description}" if description else ""
        print(f"[{row['platform_id']}] {row['section']} | {row['title']} | {row['url']}{suffix}")


def command_ingest(args: argparse.Namespace) -> int:
    platforms = load_platforms(args.platforms)
    conn = connect_db(args.db)
    init_db(conn)
    upsert_platforms(conn, platforms)
    run_id = start_ingest_run(conn)
    notes: list[str] = []

    try:
        for platform in platforms:
            try:
                records = fetch_and_parse_platform(platform, timeout=args.timeout)
                replace_platform_documents(conn, platform["id"], records)
                print(f"Ingested {len(records)} docs for {platform['name']}")
            except (HTTPError, URLError) as exc:
                message = f"{platform['id']}: fetch failed ({exc})"
                notes.append(message)
                print(message, file=sys.stderr)
            except Exception as exc:  # noqa: BLE001
                message = f"{platform['id']}: unexpected error ({exc})"
                notes.append(message)
                print(message, file=sys.stderr)

        status = "completed" if not notes else "completed_with_errors"
        finish_ingest_run(conn, run_id, status=status, notes="\n".join(notes))
        if args.export_dir:
            files = export_platform_csvs(conn, args.export_dir, markdown_only=args.markdown_only)
            for file_path in files:
                print(f"Exported {file_path}")
        return 0 if status == "completed" else 1
    finally:
        conn.close()


def command_seed_spreadsheets(args: argparse.Namespace) -> int:
    platforms = load_platforms(args.platforms)
    output_dir = Path(args.out)
    output_dir.mkdir(parents=True, exist_ok=True)
    exit_code = 0
    for platform in platforms:
        try:
            records = fetch_and_parse_platform(platform, timeout=args.timeout)
            if args.markdown_only:
                records = [record for record in records if record["is_markdown"]]
            path = export_records_csv(output_dir / f"{platform['id']}.csv", records)
            print(f"Wrote {path}")
        except (HTTPError, URLError) as exc:
            exit_code = 1
            print(f"{platform['id']}: fetch failed ({exc})", file=sys.stderr)
    return exit_code


def command_export_csv(args: argparse.Namespace) -> int:
    conn = connect_db(args.db)
    try:
        files = export_platform_csvs(conn, args.out, markdown_only=args.markdown_only)
    finally:
        conn.close()
    for file_path in files:
        print(file_path)
    return 0


def command_query(args: argparse.Namespace) -> int:
    conn = connect_db(args.db)
    try:
        rows = query_documents(
            conn,
            platform=args.platform,
            section=args.section,
            search=args.search,
            markdown_only=args.markdown_only,
            limit=args.limit,
        )
    finally:
        conn.close()

    records = [dict(row) for row in rows]
    if args.json:
        print(json.dumps(records, indent=2))
    else:
        print_rows(records)
    return 0


def command_context(args: argparse.Namespace) -> int:
    conn = connect_db(args.db)
    try:
        rows = query_documents(
            conn,
            platform=args.platform,
            section=args.section,
            search=args.search,
            markdown_only=args.markdown_only,
            limit=args.limit,
        )
    finally:
        conn.close()
    print(build_context(rows, question=args.question))
    return 0


def command_ask(args: argparse.Namespace) -> int:
    conn = connect_db(args.db)
    try:
        rows = query_documents(
            conn,
            platform=args.platform,
            section=args.section,
            search=args.search,
            markdown_only=args.markdown_only,
            limit=args.limit,
        )
    finally:
        conn.close()

    context = build_context(rows, question=args.question)
    try:
        answer = ask_openai(question=args.question, context=context, model=args.model)
    except OpenAIClientError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(answer)
    return 0


def command_serve(args: argparse.Namespace) -> int:
    serve(args.db, args.static_dir, args.host, args.port)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Documentation database toolkit for llms.txt indexes")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser("ingest", help="Ingest llms.txt sources into SQLite")
    ingest.add_argument("--db", required=True)
    ingest.add_argument("--platforms", required=True)
    ingest.add_argument("--export-dir")
    ingest.add_argument("--timeout", type=int, default=30)
    ingest.add_argument("--markdown-only", action="store_true")
    ingest.set_defaults(func=command_ingest)

    seed = subparsers.add_parser("seed-spreadsheets", help="Fetch llms.txt sources and write CSVs directly")
    seed.add_argument("--platforms", required=True)
    seed.add_argument("--out", required=True)
    seed.add_argument("--timeout", type=int, default=30)
    seed.add_argument("--markdown-only", action="store_true")
    seed.set_defaults(func=command_seed_spreadsheets)

    export_csv = subparsers.add_parser("export-csv", help="Export per-platform CSVs from the SQLite database")
    export_csv.add_argument("--db", required=True)
    export_csv.add_argument("--out", required=True)
    export_csv.add_argument("--markdown-only", action="store_true")
    export_csv.set_defaults(func=command_export_csv)

    query = subparsers.add_parser("query", help="Query the indexed docs")
    query.add_argument("--db", required=True)
    query.add_argument("--platform")
    query.add_argument("--section")
    query.add_argument("--search")
    query.add_argument("--limit", type=int, default=25)
    query.add_argument("--markdown-only", action="store_true")
    query.add_argument("--json", action="store_true")
    query.set_defaults(func=command_query)

    context = subparsers.add_parser("context", help="Build LLM-ready context from filtered docs")
    context.add_argument("--db", required=True)
    context.add_argument("--platform")
    context.add_argument("--section")
    context.add_argument("--search")
    context.add_argument("--question")
    context.add_argument("--limit", type=int, default=25)
    context.add_argument("--markdown-only", action="store_true")
    context.set_defaults(func=command_context)

    ask = subparsers.add_parser("ask", help="Ask OpenAI using filtered documentation index context")
    ask.add_argument("--db", required=True)
    ask.add_argument("--question", required=True)
    ask.add_argument("--model")
    ask.add_argument("--platform")
    ask.add_argument("--section")
    ask.add_argument("--search")
    ask.add_argument("--limit", type=int, default=20)
    ask.add_argument("--markdown-only", action="store_true")
    ask.set_defaults(func=command_ask)

    serve_parser = subparsers.add_parser("serve", help="Run the local docs browser")
    serve_parser.add_argument("--db", required=True)
    serve_parser.add_argument("--static-dir", default="web")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8765)
    serve_parser.set_defaults(func=command_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

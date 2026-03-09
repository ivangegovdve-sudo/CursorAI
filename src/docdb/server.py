from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .openai_client import OpenAIClientError, ask_openai
from .storage import build_context, connect_db, list_platforms, list_sections, query_documents


def _parse_bool(value: str | None) -> bool:
    return value in {"1", "true", "True", "yes", "on"}


def _get_single(params: dict[str, list[str]], name: str, default: str | None = None) -> str | None:
    values = params.get(name)
    if not values:
        return default
    return values[0]


def make_handler(db_path: str | Path, static_dir: str | Path):
    resolved_db_path = Path(db_path)
    resolved_static_dir = Path(static_dir)

    class DocDbHandler(BaseHTTPRequestHandler):
        server_version = "CursorAIDocDb/0.1"

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                return self._serve_file(resolved_static_dir / "index.html", "text/html; charset=utf-8")
            if parsed.path == "/api/platforms":
                return self._handle_platforms()
            if parsed.path == "/api/sections":
                return self._handle_sections(parsed.query)
            if parsed.path == "/api/docs":
                return self._handle_docs(parsed.query)
            if parsed.path == "/api/context":
                return self._handle_context(parsed.query)
            self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/api/ask":
                return self._handle_ask()
            self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _get_connection(self):
            return connect_db(resolved_db_path)

        def _serve_file(self, path: Path, content_type: str) -> None:
            if not path.exists():
                self._send_json({"error": "Static file not found"}, status=HTTPStatus.NOT_FOUND)
                return
            data = path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
            data = json.dumps(payload, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _read_json_body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b"{}"
            return json.loads(raw.decode("utf-8") or "{}")

        def _handle_platforms(self) -> None:
            conn = self._get_connection()
            try:
                payload = {"platforms": [dict(row) for row in list_platforms(conn)]}
            finally:
                conn.close()
            self._send_json(payload)

        def _handle_sections(self, query_string: str) -> None:
            params = parse_qs(query_string)
            platform = _get_single(params, "platform")
            conn = self._get_connection()
            try:
                payload = {"sections": list_sections(conn, platform=platform)}
            finally:
                conn.close()
            self._send_json(payload)

        def _query_rows(self, params: dict[str, list[str]]):
            platform = _get_single(params, "platform")
            section = _get_single(params, "section")
            search = _get_single(params, "search")
            markdown_only = _parse_bool(_get_single(params, "markdown_only", "1"))
            limit = min(int(_get_single(params, "limit", "100") or "100"), 500)
            conn = self._get_connection()
            try:
                rows = query_documents(
                    conn,
                    platform=platform or None,
                    section=section or None,
                    search=search or None,
                    markdown_only=markdown_only,
                    limit=limit,
                )
                return [dict(row) for row in rows]
            finally:
                conn.close()

        def _handle_docs(self, query_string: str) -> None:
            params = parse_qs(query_string)
            rows = self._query_rows(params)
            self._send_json({"documents": rows, "count": len(rows)})

        def _handle_context(self, query_string: str) -> None:
            params = parse_qs(query_string)
            question = _get_single(params, "question")
            rows = self._query_rows(params)
            context = build_context(rows, question=question or None)
            self._send_json({"context": context, "count": len(rows)})

        def _handle_ask(self) -> None:
            payload = self._read_json_body()
            params = {
                "platform": [payload.get("platform", "")],
                "section": [payload.get("section", "")],
                "search": [payload.get("search", "")],
                "markdown_only": ["1" if payload.get("markdown_only", True) else "0"],
                "limit": [str(payload.get("limit", 20))],
            }
            question = str(payload.get("question", "")).strip()
            if not question:
                self._send_json({"error": "Question is required."}, status=HTTPStatus.BAD_REQUEST)
                return

            rows = self._query_rows(params)
            context = build_context(rows, question=question)
            try:
                answer = ask_openai(question=question, context=context, model=payload.get("model"))
            except OpenAIClientError as exc:
                self._send_json({"error": str(exc), "context": context}, status=HTTPStatus.BAD_REQUEST)
                return

            self._send_json({"answer": answer, "context": context, "count": len(rows)})

    return DocDbHandler


def serve(db_path: str | Path, static_dir: str | Path, host: str, port: int) -> None:
    handler = make_handler(db_path=db_path, static_dir=static_dir)
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Serving docs database on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

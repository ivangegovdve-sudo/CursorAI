from __future__ import annotations

import json
from http.server import ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen

from docdb.server import make_handler


class FakeControlPlane:
    def load_runs(self, limit: int = 20) -> list[dict[str, object]]:
        return [{"repo": "cursorai", "status": "done"}]

    def roadmap_snapshot(self, repo: str) -> dict[str, object]:
        return {"repo": repo, "roadmap": {"title": "Test", "tasks": []}}

    def run_next(self, repo: str) -> dict[str, object]:
        return {"repo": repo, "status": "done"}

    def start_scheduler(self, interval_seconds: int = 300) -> dict[str, object]:
        return {"running": True, "interval_seconds": interval_seconds}

    def status_snapshot(self) -> dict[str, object]:
        return {
            "active_run": None,
            "repos": {"cursorai": self.roadmap_snapshot("cursorai")},
            "scheduler": {"running": False, "interval_seconds": 300},
        }

    def stop_scheduler(self) -> dict[str, object]:
        return {"running": False}


class ServerAdkApiTests(unittest.TestCase):
    def test_adk_status_and_run_next_endpoints(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            web_dir = tmp_path / "web"
            ui_dir = tmp_path / "ui"
            web_dir.mkdir()
            ui_dir.mkdir()
            (web_dir / "index.html").write_text("web", encoding="utf-8")
            (ui_dir / "index.html").write_text("ui", encoding="utf-8")

            with patch("docdb.server.create_control_plane_service", return_value=FakeControlPlane()):
                handler = make_handler(db_path=tmp_path / "db.sqlite3", static_dir=web_dir)
                server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    base_url = f"http://127.0.0.1:{server.server_port}"
                    with urlopen(f"{base_url}/api/adk/status") as response:
                        payload = json.loads(response.read().decode("utf-8"))
                    self.assertIn("scheduler", payload)

                    request = Request(
                        f"{base_url}/api/adk/run-next",
                        data=json.dumps({"repo": "cursorai"}).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with urlopen(request) as response:
                        run_payload = json.loads(response.read().decode("utf-8"))
                    self.assertEqual(run_payload["status"], "done")
                finally:
                    server.shutdown()
                    server.server_close()

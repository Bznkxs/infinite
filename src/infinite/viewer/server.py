"""`infinite-viewer` — serve the runs directory as a browsable dialogue.

Stdlib http.server, no build step: the page is one static file that talks to
three JSON endpoints.

    GET /                                       the page
    GET /api/workspaces                          every workspace and its agents
    GET /api/trajectory?workspace=..&agent=..    one normalized trajectory
"""

from __future__ import annotations

import argparse
import json
import webbrowser
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .reader import list_workspaces, load_trajectory, trajectory_path

PAGE = Path(__file__).parent / "index.html"


class Handler(BaseHTTPRequestHandler):
    server_version = "infinite-viewer"

    def __init__(self, *args, root: Path, **kwargs):
        self.root = root
        super().__init__(*args, **kwargs)

    # --- plumbing ------------------------------------------------------
    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def log_message(self, fmt, *args) -> None:  # quieter than the default
        pass

    # --- routes --------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802 (http.server's API)
        url = urlparse(self.path)
        query = parse_qs(url.query)
        try:
            if url.path in ("/", "/index.html"):
                self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            elif url.path == "/api/workspaces":
                self._json(
                    {"root": str(self.root), "workspaces": list_workspaces(self.root)}
                )
            elif url.path == "/api/trajectory":
                workspace = (query.get("workspace") or [""])[0]
                agent = (query.get("agent") or [""])[0]
                path = trajectory_path(self.root, workspace, agent)
                self._json(load_trajectory(path, workspace))
            else:
                self._json({"error": f"no route for {url.path}"}, status=404)
        except FileNotFoundError as exc:
            self._json({"error": f"not found: {exc}"}, status=404)
        except ValueError as exc:
            self._json({"error": str(exc)}, status=400)
        except Exception as exc:  # a bad trajectory must not kill the server
            self._json({"error": f"{type(exc).__name__}: {exc}"}, status=500)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="infinite-viewer", description=__doc__)
    parser.add_argument("root", nargs="?", default="runs", help="The runs directory.")
    parser.add_argument("-p", "--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--no-open", action="store_true", help="Do not open a browser.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"no such directory: {root}")
        return 1

    server = ThreadingHTTPServer(
        (args.host, args.port), partial(Handler, root=root)
    )
    url = f"http://{args.host}:{server.server_address[1]}/"
    print(f"serving {root} at {url}  (ctrl-c to stop)")
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Jupyter Server Proxy configuration for AiiDAlab EXAFS.

Provides entry points for `jupyter-server-proxy` to supervise:

1. ``exafs-marimo`` — Marimo app server (``debye_waller.py``, ``paths_explorer.py``)
2. ``exafs-restapi`` — the local AiiDA REST API (``verdi restapi``)
3. ``exafs-explorer`` — the ``aiida-explorer`` single-page app (built in the image)

All three bind to ``127.0.0.1`` and are reachable only through Jupyter's
authenticated reverse proxy at ``{base_url}<name>/``.
"""

from __future__ import annotations

import os
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def find_app_dir() -> Path:
    """Locate the app checkout that holds ``notebooks/`` and ``explorer/``."""
    env_dir = os.environ.get("AIIDALAB_EXAFS_APP_DIR")
    if env_dir and Path(env_dir).is_dir():
        return Path(env_dir).resolve()

    candidates = [
        Path.home() / "apps" / "exafs",
        Path.home() / "apps" / "aiidalab-exafs",
        Path("/opt/aiidalab-exafs/app"),
        # src/aiidalab_exafs/proxy.py -> repo root, for editable/dev installs
        Path(__file__).resolve().parent.parent.parent,
        Path.cwd(),
    ]

    for candidate in candidates:
        if (candidate / "notebooks" / "debye_waller.py").is_file():
            return candidate.resolve()

    return (Path.home() / "apps" / "exafs").resolve()


def find_notebooks_dir() -> Path:
    """Return the directory holding the Marimo notebooks."""
    env_dir = os.environ.get("AIIDALAB_EXAFS_NOTEBOOKS_DIR")
    if env_dir and Path(env_dir).is_dir():
        return Path(env_dir).resolve()
    return find_app_dir() / "notebooks"


def find_explorer_dir() -> Path:
    """Return the directory holding the built aiida-explorer app.

    The container image builds it from upstream source into
    ``/opt/aiidalab-exafs/explorer`` (see ``docker/base/Dockerfile``).
    """
    env_dir = os.environ.get("AIIDALAB_EXAFS_EXPLORER_DIR")
    if env_dir and Path(env_dir).is_dir():
        return Path(env_dir).resolve()
    image_dir = Path("/opt/aiidalab-exafs/explorer")
    if image_dir.is_dir():
        return image_dir
    return find_app_dir() / "explorer"


def patch_jsp_empty_subprotocol() -> None:
    """Stop jupyter-server-proxy 3.x sending an empty Sec-WebSocket-Protocol header.

    tornado calls ``select_subprotocol([])`` when the client offers no
    subprotocol, which a browser never does for marimo. jsp 3.x stores that
    empty list and later passes it to ``websocket_connect``, which then sends
    a literally empty ``Sec-WebSocket-Protocol`` header. uvicorn rejects that
    with HTTP 400, so the proxied websocket never reaches marimo.

    Fixed upstream in jupyter-server-proxy 4.x, so this is a no-op there; it is
    only needed for 3.x on the classic Notebook server of older AiiDAlab images.
    This is called from :func:`setup_marimo`, which jupyter-server-proxy
    invokes once at server start, before any handler is built.
    """
    try:
        import jupyter_server_proxy
        from jupyter_server_proxy import handlers as jsp_handlers
    except ImportError:  # pragma: no cover - proxy is optional at import time
        return

    major = jupyter_server_proxy.__version__.split(".")[0]
    if major.isdigit() and int(major) >= 4:
        return

    cls = jsp_handlers.ProxyHandler
    if getattr(cls, "_exafs_subprotocol_patched", False):
        return

    original = cls.select_subprotocol

    def select_subprotocol(self, subprotocols):
        selected = original(self, subprotocols)
        if not self.subprotocols:
            self.subprotocols = None
        return selected

    cls.select_subprotocol = select_subprotocol
    cls._exafs_subprotocol_patched = True


def setup_marimo() -> dict:
    """Return the jupyter-server-proxy configuration for the Marimo app server."""
    patch_jsp_empty_subprotocol()
    notebooks_dir = str(find_notebooks_dir())
    extra_args: list[str] = []
    allow_origins = os.environ.get("MARIMO_ALLOW_ORIGINS")
    if allow_origins:
        extra_args.extend(["--allow-origins", allow_origins])

    return {
        "command": [
            "marimo",
            "run",
            notebooks_dir,
            "--host",
            "127.0.0.1",
            "-p",
            "{port}",
            "--headless",
            "--no-token",
            # marimo rejects a --base-url with a trailing slash, and
            # jupyter-server-proxy's {base_url} always ends in one.
            "--base-url",
            "{base_url}exafs-marimo",
            *extra_args,
        ],
        # marimo is told its own prefix, so it must receive the full path.
        "absolute_url": True,
        "timeout": 60,
        "request_headers_override": {
            # jupyter-server-proxy 3.x copies every client header to the
            # backend, including the browser's
            # `Sec-WebSocket-Extensions: permessage-deflate`. But it dials the
            # backend with a tornado client that never negotiated compression,
            # so when marimo accepts permessage-deflate tornado aborts the
            # connection with "unsupported extension" and the browser sees a
            # 1006 close part-way through "Connecting". Replacing the header
            # with a token no server will negotiate keeps the socket
            # uncompressed and stable. curl never sends this header, which is
            # why a handshake test passes while a real browser fails.
            "Sec-WebSocket-Extensions": "identity",
        },
        "launcher_entry": {"title": "EXAFS Marimo", "enabled": False},
    }


def setup_restapi() -> dict:
    """Return the jupyter-server-proxy configuration for the AiiDA REST API."""
    return {
        "command": [
            "verdi",
            "restapi",
            "--hostname",
            "127.0.0.1",
            "--port",
            "{port}",
        ],
        # verdi restapi has no prefix option, so strip it before forwarding.
        "absolute_url": False,
        "timeout": 60,
        "launcher_entry": {"title": "AiiDA REST API", "enabled": False},
    }


def setup_explorer() -> dict:
    """Return the jupyter-server-proxy configuration for the aiida-explorer SPA.

    The build is served through the proxy rather than through Jupyter's
    ``/files/`` endpoint: ``/files/`` responses carry a
    ``Content-Security-Policy: sandbox allow-scripts`` header, which gives the
    page an opaque origin. An opaque-origin document cannot send the Jupyter
    session cookie, so its requests to the proxied REST API would be rejected.
    """
    return {
        "command": [
            sys.executable,
            # Run the file itself: `-m aiidalab_exafs.proxy` would import the whole
            # app package (aiida, feff, ...) just to serve static files.
            str(Path(__file__).resolve()),
            "{port}",
            str(find_explorer_dir()),
        ],
        "absolute_url": False,
        "timeout": 30,
        "launcher_entry": {"title": "AiiDA Explorer", "enabled": False},
    }


class _NoCacheHandler(SimpleHTTPRequestHandler):
    """Static handler that forces revalidation.

    Hashed asset names change on every rebuild, but ``index.html`` does not.
    Without a Cache-Control header browsers cache it heuristically and keep
    loading stale asset names after the explorer is rebuilt.
    """

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()


def serve_explorer(port: int, directory: str) -> None:
    """Serve ``directory`` on 127.0.0.1:``port`` with revalidation forced."""
    handler = partial(_NoCacheHandler, directory=directory)
    ThreadingHTTPServer(("127.0.0.1", port), handler).serve_forever()


def proxy_url_js(endpoint: str, query: str = "") -> str:
    """Return inline JavaScript that opens a proxied endpoint in a new tab.

    Reads Jupyter's ``data-base-url`` attribute so links keep working under
    JupyterHub or any other sub-path deployment.
    """
    clean_query = query.lstrip("?")
    query_str = f"?{clean_query}" if clean_query else ""
    return (
        "(function(){"
        "var b = document.body && document.body.getAttribute('data-base-url') || '/';"
        "if (!b.endsWith('/')) b += '/';"
        f"window.open(b + '{endpoint}/' + '{query_str}', '_blank');"
        "})()"
    )


if __name__ == "__main__":
    serve_explorer(int(sys.argv[1]), sys.argv[2])

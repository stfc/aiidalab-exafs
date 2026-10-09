"""Widget for downloading data reliably in Jupyter and AiiDAlab environments."""

from __future__ import annotations

import base64
import mimetypes
from collections.abc import Callable
from typing import Any

import ipywidgets as ipw
from IPython.display import Javascript


class Download(ipw.Button):
    """Widget for downloading data using Blob URLs to support binary & large files reliably.

    Replaces alc_aiidalab_widgets.widgets.download.Download to:
    1. Use standard Base64 (RFC 4648) instead of urlsafe_b64encode (which produces illegal
       '-' and '_' characters in data URIs).
    2. Use Blob + URL.createObjectURL instead of data: URIs, avoiding browser URL length and
       navigation restrictions.
    3. Append the anchor to document.body before clicking (required by Firefox to trigger
       downloads).
    """

    def __init__(
        self,
        filename: str,
        *,
        cb: Callable[[], str | bytes],
        output: ipw.Output,
        mimetype: str = "",
        **kwargs: Any,
    ) -> None:
        """Initialize Download widget."""
        super().__init__(**kwargs)
        self.output = output
        self.cb = cb
        self.filename = filename
        if not mimetype:
            mimetype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        self.mimetype = mimetype
        self.on_click(self._download)

    def _download(self, _b: Any = None) -> None:
        data = self.cb()
        if not data:
            return
        if isinstance(data, str):
            data = data.encode("utf-8")

        payload = base64.b64encode(data).decode("ascii")
        mimetype = self.mimetype or "application/octet-stream"
        filename = self.filename

        action = Javascript(f"""
        (function() {{
            var b64 = "{payload}";
            var bin = atob(b64);
            var len = bin.length;
            var u8 = new Uint8Array(len);
            for (var i = 0; i < len; i++) {{
                u8[i] = bin.charCodeAt(i);
            }}
            var blob = new Blob([u8], {{type: "{mimetype}"}});
            var url = URL.createObjectURL(blob);
            var a = document.createElement("a");
            a.style.display = "none";
            a.href = url;
            a.download = "{filename}";
            document.body.appendChild(a);
            a.click();
            setTimeout(function() {{
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
            }}, 1500);
        }})();
        """)

        self.output.append_display_data(action)
        self.output.clear_output()

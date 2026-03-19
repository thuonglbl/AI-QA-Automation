"""Local HTTP/1.1 → HTTP/2 reverse proxy for .NET compatibility.

.NET HttpClient cannot send HTTP/2 when the server doesn't negotiate h2
via ALPN. This proxy accepts HTTP/1.1 on localhost:8000 and forwards to
the AI server via forced HTTP/2.

Usage: python h2_proxy.py
"""

import os
os.environ["PYTHONUTF8"] = "1"

from http.server import HTTPServer, BaseHTTPRequestHandler
import httpx
import yaml

# Load config
with open("config.yaml", encoding="utf-8") as f:
    cfg = yaml.safe_load(f)["ai_server"]

BASE_URL = cfg["base_url"].rstrip("/")
API_KEY = os.environ.get("AI_API_KEY") or cfg["api_key"]
VERIFY = cfg.get("verify_ssl", False)
TIMEOUT = cfg.get("timeout", 120)

# Persistent HTTP/2 client
h2_client = httpx.Client(
    http1=False,
    http2=True,
    verify=VERIFY,
    timeout=httpx.Timeout(connect=10, read=TIMEOUT, write=30, pool=10),
    headers={"Authorization": f"Bearer {API_KEY}"},
)


class ProxyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self._proxy("GET")

    def do_POST(self):
        self._proxy("POST")

    def _proxy(self, method):
        url = f"{BASE_URL}{self.path}"
        body = None
        if method == "POST":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else None

        try:
            r = h2_client.request(
                method, url,
                content=body,
                headers={"Content-Type": self.headers.get("Content-Type", "application/json")},
            )
            self.send_response(r.status_code)
            self.send_header("Content-Type", r.headers.get("content-type", "application/json"))
            self.end_headers()
            self.wfile.write(r.content)
        except Exception as e:
            self.send_response(502)
            self.end_headers()
            self.wfile.write(f'{{"error": "{e}"}}'.encode())

    def log_message(self, format, *args):
        print(f"[proxy] {args[0]}")


if __name__ == "__main__":
    port = 8000
    print(f"H2 Proxy: localhost:{port} -> {BASE_URL}")
    print(f"Model: {cfg['model']}")
    print("Waiting for requests... (Ctrl+C to stop)\n")
    HTTPServer(("127.0.0.1", port), ProxyHandler).serve_forever()

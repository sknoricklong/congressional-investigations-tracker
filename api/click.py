"""Vercel serverless function: track link clicks.

Receives POST with click data, stores in Vercel KV (Upstash Redis).
"""
import json
import os
import urllib.request
from http.server import BaseHTTPRequestHandler

KV_URL = os.environ.get("KV_REST_API_URL", "")
KV_TOKEN = os.environ.get("KV_REST_API_TOKEN", "")


def _kv_command(command: list) -> dict:
    """Send a command to Vercel KV via REST API."""
    if not KV_URL or not KV_TOKEN:
        return {"error": "KV not configured"}

    data = json.dumps(command).encode()
    req = urllib.request.Request(
        KV_URL,
        data=data,
        headers={
            "Authorization": f"Bearer {KV_TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else b"{}"
            click = json.loads(body)

            # Validate required fields
            if not click.get("url"):
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error":"missing url"}')
                return

            # Store as JSON string in a Redis list
            event = json.dumps({
                "url": click.get("url", ""),
                "title": click.get("title", ""),
                "source": click.get("source", ""),
                "committee": click.get("committee", ""),
                "timestamp": click.get("timestamp", ""),
            })
            _kv_command(["LPUSH", "clicks", event])

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')

        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

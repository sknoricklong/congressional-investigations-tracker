"""Vercel serverless function: return click analytics.

Reads click events from Vercel KV and returns as JSON.
"""
import json
import os
import urllib.request
from http.server import BaseHTTPRequestHandler

KV_URL = os.environ.get("KV_REST_API_URL", "")
KV_TOKEN = os.environ.get("KV_REST_API_TOKEN", "")


def _kv_command(command: list) -> dict:
    if not KV_URL or not KV_TOKEN:
        return {"result": []}

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
    def do_GET(self):
        try:
            # Get all click events (last 10000)
            result = _kv_command(["LRANGE", "clicks", "0", "9999"])
            events = []
            for raw in result.get("result", []):
                try:
                    events.append(json.loads(raw))
                except (json.JSONDecodeError, TypeError):
                    pass

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"clicks": events, "total": len(events)}).encode())

        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

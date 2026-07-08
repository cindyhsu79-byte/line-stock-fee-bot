import base64
import hashlib
import hmac
import json
import os
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from stock_fee_bot.fees import InvalidMessageError, format_help, format_reply, parse_message, should_ignore_text


LINE_REPLY_URL = "https://api.line.me/v2/bot/message/reply"


class LineBotHandler(BaseHTTPRequestHandler):
    server_version = "LineStockFeeBot/1.0"

    def do_GET(self):
        if self.path == "/health":
            self._send_json(200, {"ok": True})
            return

        self._send_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/callback":
            self._send_json(404, {"error": "not found"})
            return

        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        if not self._is_valid_signature(body):
            print("Rejected webhook: invalid LINE signature", flush=True)
            self._send_json(403, {"error": "invalid signature"})
            return

        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            print("Rejected webhook: invalid JSON", flush=True)
            self._send_json(400, {"error": "invalid json"})
            return

        events = payload.get("events", [])
        print(f"Webhook received: {len(events)} event(s)", flush=True)
        for event in events:
            self._handle_event(event)

        self._send_json(200, {"ok": True})

    def log_message(self, format, *args):
        return

    def _handle_event(self, event):
        if event.get("type") != "message":
            print(f"Skipped event type: {event.get('type')}", flush=True)
            return

        message = event.get("message", {})
        if message.get("type") != "text":
            print(f"Skipped message type: {message.get('type')}", flush=True)
            return

        text = message.get("text", "")
        reply_token = event.get("replyToken")
        if not reply_token:
            print("Skipped text event: missing reply token", flush=True)
            return

        if should_ignore_text(text):
            print(f"Skipped chat text: {text!r}", flush=True)
            return

        try:
            reply_text = format_reply(parse_message(text))
        except (InvalidMessageError, ValueError):
            reply_text = format_help()

        print(f"Replying to text event: {text!r}", flush=True)
        reply_to_line(reply_token, reply_text)

    def _is_valid_signature(self, body):
        secret = os.environ.get("LINE_CHANNEL_SECRET")
        if not secret:
            return True

        signature = self.headers.get("X-Line-Signature", "")
        digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
        expected = base64.b64encode(digest).decode("utf-8")
        return hmac.compare_digest(signature, expected)

    def _send_json(self, status, payload):
        response = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)


def reply_to_line(reply_token, text):
    access_token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    if not access_token:
        print(text)
        return

    body = json.dumps(
        {
            "replyToken": reply_token,
            "messages": [{"type": "text", "text": text}],
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        LINE_REPLY_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            response.read()
            print(f"LINE reply succeeded: HTTP {response.status}", flush=True)
    except urllib.error.URLError as error:
        print(f"LINE reply failed: {error}", flush=True)


def run(host="0.0.0.0", port=None):
    resolved_port = int(port or os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer((host, resolved_port), LineBotHandler)
    print(f"LINE stock fee bot listening on http://{host}:{resolved_port}", flush=True)
    server.serve_forever()

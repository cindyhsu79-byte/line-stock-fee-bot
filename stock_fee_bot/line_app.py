import base64
import hashlib
import hmac
import json
import os
import urllib.error
import urllib.request
from datetime import datetime
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from zoneinfo import ZoneInfo

from stock_fee_bot.fees import InvalidMessageError, format_help, format_reply, parse_message, should_ignore_text
from stock_fee_bot.quote import StockQuote, StockQuoteError, fetch_index_quote, fetch_stock_quote


LINE_REPLY_URL = "https://api.line.me/v2/bot/message/reply"
LINE_BROADCAST_URL = "https://api.line.me/v2/bot/message/broadcast"
SCHEDULED_QUOTES_PATH = "/scheduled-quotes"
MARKET_QUOTE_COMMAND = "行情"
SCHEDULED_STOCK_CODES = ("2330", "2454", "2308")
TAIPEI_TIMEZONE = ZoneInfo("Asia/Taipei")


class LineBotHandler(BaseHTTPRequestHandler):
    server_version = "LineStockFeeBot/1.0"

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/health":
            self._send_json(200, {"ok": True})
            return

        if path == SCHEDULED_QUOTES_PATH:
            if not self._is_valid_schedule_request():
                print("Rejected scheduled quote request: invalid schedule token", flush=True)
                self._send_json(403, {"error": "invalid schedule token"})
                return

            try:
                message = format_scheduled_quotes()
                broadcast_to_line(message)
            except Exception as error:
                print(f"Scheduled quote broadcast failed: {error}", flush=True)
                self._send_json(500, {"ok": False, "error": "scheduled quotes failed"})
                return

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

        if text.strip() == MARKET_QUOTE_COMMAND:
            reply_text = format_scheduled_quotes()
            print(f"Replying to market quote command: {text!r}", flush=True)
            reply_to_line(reply_token, reply_text)
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

    def _is_valid_schedule_request(self):
        token = os.environ.get("SCHEDULE_TOKEN")
        if not token:
            return True

        provided_token = self.headers.get("X-Schedule-Token", "")
        return hmac.compare_digest(provided_token, token)

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


def broadcast_to_line(text, urlopen=urllib.request.urlopen):
    access_token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    if not access_token:
        print(text)
        return

    body = json.dumps(
        {
            "messages": [{"type": "text", "text": text}],
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        LINE_BROADCAST_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urlopen(request, timeout=10) as response:
            response.read()
            print(f"LINE broadcast succeeded: HTTP {response.status}", flush=True)
    except urllib.error.URLError as error:
        print(f"LINE broadcast failed: {error}", flush=True)
        raise


def format_scheduled_quotes(
    now=None,
    quote_lookup=fetch_stock_quote,
    index_lookup=fetch_index_quote,
) -> str:
    current_time = now or datetime.now(TAIPEI_TIMEZONE)
    lines = [f"今日行情 {current_time.strftime('%H:%M')}"]

    try:
        index_quote = index_lookup("大盤")
        lines.append(_format_scheduled_quote_line("大盤", index_quote, "點"))
    except StockQuoteError:
        lines.append("大盤 查價失敗")

    for stock_code in SCHEDULED_STOCK_CODES:
        try:
            quote = quote_lookup(stock_code)
            lines.append(_format_scheduled_quote_line(stock_code, quote, "元"))
        except StockQuoteError:
            lines.append(f"{stock_code} 查價失敗")

    return "\n".join(lines)


def _format_scheduled_quote_line(label: str, quote: StockQuote, unit: str) -> str:
    title = label if not quote.stock_code else f"{quote.stock_code} {quote.name}"
    price = f"{_format_decimal(quote.price)}{unit}"
    change = _format_change_percent(quote.change_percent)
    return f"{title} {price}{change}"


def _format_change_percent(change_percent: Decimal | None) -> str:
    if change_percent is None:
        return ""

    sign = "+" if change_percent >= 0 else ""
    return f" {sign}{_format_decimal(change_percent)}%"


def _format_decimal(value: Decimal) -> str:
    return f"{value.normalize():f}"


def run(host="0.0.0.0", port=None):
    resolved_port = int(port or os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer((host, resolved_port), LineBotHandler)
    print(f"LINE stock fee bot listening on http://{host}:{resolved_port}", flush=True)
    server.serve_forever()

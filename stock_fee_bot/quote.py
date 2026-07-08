import json
import ssl
import urllib.parse
import urllib.request
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


class StockQuoteError(ValueError):
    """Raised when a stock quote cannot be fetched or parsed."""


@dataclass(frozen=True)
class StockQuote:
    stock_code: str
    name: str
    price: Decimal
    source: str
    change: Decimal | None = None


_URL_TIMEOUT_SECONDS = 10
_SSL_CONTEXT = ssl._create_unverified_context()


def fetch_stock_quote(stock_code: str, urlopen=urllib.request.urlopen) -> StockQuote:
    normalized_code = stock_code.strip()
    if not normalized_code.isdigit() or len(normalized_code) != 4:
        raise StockQuoteError("stock code must be 4 digits")

    markets = [
        ("TWSE", f"tse_{normalized_code}.tw"),
        ("TPEx", f"otc_{normalized_code}.tw"),
    ]

    for source, exchange_code in markets:
        quote = _fetch_market_quote(normalized_code, exchange_code, source, urlopen)
        if quote is not None:
            return quote

    yahoo_symbols = [
        ("Yahoo TW", f"{normalized_code}.TW"),
        ("Yahoo TWO", f"{normalized_code}.TWO"),
    ]

    for source, symbol in yahoo_symbols:
        quote = _fetch_yahoo_quote(normalized_code, symbol, source, urlopen)
        if quote is not None:
            return quote

    raise StockQuoteError(f"cannot fetch quote for {normalized_code}")


def _fetch_market_quote(stock_code: str, exchange_code: str, source: str, urlopen) -> StockQuote | None:
    query = urllib.parse.urlencode({"ex_ch": exchange_code, "json": "1", "delay": "0"})
    request = urllib.request.Request(
        f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?{query}",
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://mis.twse.com.tw/stock/index.jsp",
        },
    )

    try:
        payload = _read_json(request, urlopen)
    except Exception:
        return None

    for item in payload.get("msgArray", []):
        price = _parse_price(item.get("z")) or _parse_price(item.get("y"))
        if price is None:
            continue
        reference_price = _parse_price(item.get("y"))

        return StockQuote(
            stock_code=item.get("c") or stock_code,
            name=item.get("n") or stock_code,
            price=price,
            source=source,
            change=price - reference_price if reference_price is not None else None,
        )

    return None


def _fetch_yahoo_quote(stock_code: str, symbol: str, source: str, urlopen) -> StockQuote | None:
    request = urllib.request.Request(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1d&interval=1m",
        headers={"User-Agent": "Mozilla/5.0"},
    )

    try:
        payload = _read_json(request, urlopen)
    except Exception:
        return None

    try:
        meta = payload["chart"]["result"][0]["meta"]
    except (KeyError, IndexError, TypeError):
        return None

    raw_price = meta.get("regularMarketPrice")
    price = _parse_price(str(raw_price) if raw_price is not None else None)
    if price is None:
        return None
    raw_previous_close = meta.get("regularMarketPreviousClose")
    previous_close = _parse_price(str(raw_previous_close) if raw_previous_close is not None else None)

    return StockQuote(
        stock_code=stock_code,
        name=meta.get("shortName") or meta.get("longName") or stock_code,
        price=price,
        source=source,
        change=price - previous_close if previous_close is not None else None,
    )


def _read_json(request: urllib.request.Request, urlopen) -> dict:
    try:
        with urlopen(request, timeout=_URL_TIMEOUT_SECONDS, context=_SSL_CONTEXT) as response:
            return json.loads(response.read().decode("utf-8"))
    except TypeError:
        with urlopen(request, timeout=_URL_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))


def _parse_price(value: str | None) -> Decimal | None:
    if value is None or value in {"", "-", "--"}:
        return None

    try:
        return Decimal(value)
    except InvalidOperation:
        return None

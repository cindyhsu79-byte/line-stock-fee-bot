import json
import re
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


@dataclass(frozen=True)
class _MarketResult:
    stock_code: str
    name: str
    price: Decimal | None
    source: str


_URL_TIMEOUT_SECONDS = 10
_SSL_CONTEXT = ssl._create_unverified_context()


def fetch_stock_quote(stock_code: str, urlopen=urllib.request.urlopen) -> StockQuote:
    normalized_code = stock_code.strip()
    if not normalized_code.isdigit() or len(normalized_code) != 4:
        raise StockQuoteError("股票代號必須是 4 碼")

    preferred_name: str | None = None
    for source, exchange_code in (
        ("TWSE", f"tse_{normalized_code}.tw"),
        ("TPEx", f"otc_{normalized_code}.tw"),
    ):
        market = _fetch_market_quote(normalized_code, exchange_code, source, urlopen)
        if market is None:
            continue

        if preferred_name is None or market.name != market.stock_code:
            preferred_name = market.name
        break

    for source, symbol in (
        ("Yahoo TW", f"{normalized_code}.TW"),
        ("Yahoo TWO", f"{normalized_code}.TWO"),
    ):
        quote = _fetch_yahoo_quote(normalized_code, symbol, source, preferred_name, urlopen)
        if quote is not None:
            return quote

    raise StockQuoteError(f"查不到 {normalized_code} 的現價")


def _fetch_market_quote(
    stock_code: str,
    exchange_code: str,
    source: str,
    urlopen,
) -> _MarketResult | None:
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
        code = item.get("c") or stock_code
        name = item.get("n") or code
        price = _parse_price(item.get("z"))

        if code != stock_code:
            continue

        return _MarketResult(
            stock_code=code,
            name=name,
            price=price,
            source=source,
        )

    return None


def _fetch_yahoo_quote(
    stock_code: str,
    symbol: str,
    source: str,
    preferred_name: str | None,
    urlopen,
) -> StockQuote | None:
    request = urllib.request.Request(
        f"https://tw.stock.yahoo.com/quote/{symbol}",
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "zh-TW,zh;q=0.9",
        },
    )

    try:
        page = _read_text(request, urlopen)
    except Exception:
        return None

    symbol_pattern = re.escape(symbol)
    quote_match = re.search(
        rf'"symbol":"{symbol_pattern}".{{0,2000}}?"regularMarketPrice":(?P<price>\d+(?:\.\d+)?)',
        page,
    )
    if quote_match is None:
        return None

    price = _parse_price(quote_match.group("price"))
    if price is None:
        return None

    name = preferred_name
    name_match = re.search(r'"name":"(?P<name>[^"]+)"', quote_match.group(0))
    if name is None and name_match is not None:
        name = _decode_json_string(name_match.group("name"))

    return StockQuote(
        stock_code=stock_code,
        name=name or stock_code,
        price=price,
        source=source,
    )


def _read_json(request: urllib.request.Request, urlopen) -> dict:
    return json.loads(_read_text(request, urlopen))


def _read_text(request: urllib.request.Request, urlopen) -> str:
    try:
        with urlopen(request, timeout=_URL_TIMEOUT_SECONDS, context=_SSL_CONTEXT) as response:
            return response.read().decode("utf-8")
    except TypeError:
        with urlopen(request, timeout=_URL_TIMEOUT_SECONDS) as response:
            return response.read().decode("utf-8")


def _parse_price(value: str | None) -> Decimal | None:
    if value is None or value in {"", "-", "--", "None"}:
        return None

    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _decode_json_string(value: str) -> str:
    try:
        return json.loads(f'"{value}"')
    except json.JSONDecodeError:
        return value

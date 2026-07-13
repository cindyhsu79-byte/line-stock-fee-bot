import json
import re
import ssl
import urllib.parse
import urllib.request
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


class StockQuoteError(ValueError):
    """Raised when a stock quote cannot be fetched or parsed."""


@dataclass(frozen=True)
class StockQuote:
    stock_code: str
    name: str
    price: Decimal
    source: str
    change_percent: Decimal | None = None


@dataclass(frozen=True)
class StockSearchMatch:
    stock_code: str
    name: str
    source: str
    full_name: str = ""


@dataclass(frozen=True)
class _MarketResult:
    stock_code: str
    name: str
    price: Decimal | None
    source: str


_URL_TIMEOUT_SECONDS = 10
_SSL_CONTEXT = ssl._create_unverified_context()
_STOCK_LIST_CACHE: tuple[StockSearchMatch, ...] | None = None
_STOCK_LIST_SOURCES = (
    (
        "TWSE",
        "https://openapi.twse.com.tw/v1/opendata/t187ap03_L",
        "公司代號",
        "公司簡稱",
        "公司名稱",
    ),
    (
        "TPEx",
        "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O",
        "SecuritiesCompanyCode",
        "CompanyAbbreviation",
        "CompanyName",
    ),
)


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


def search_stock_matches(query: str, urlopen=urllib.request.urlopen) -> list[StockSearchMatch]:
    normalized_query = _normalize_name(query)
    if len(normalized_query) < 2:
        return []

    candidates = _load_stock_list(urlopen)
    exact_matches = []
    prefix_matches = []
    contains_matches = []

    for candidate in candidates:
        normalized_name = _normalize_name(candidate.name)
        normalized_full_name = _normalize_name(candidate.full_name)

        if normalized_query in {candidate.stock_code, normalized_name, normalized_full_name}:
            exact_matches.append(candidate)
        elif normalized_name.startswith(normalized_query) or normalized_full_name.startswith(normalized_query):
            prefix_matches.append(candidate)
        elif normalized_query in normalized_name or normalized_query in normalized_full_name:
            contains_matches.append(candidate)

    return _unique_matches(exact_matches or prefix_matches or contains_matches)


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

    quote_context = page[quote_match.start() : quote_match.start() + 5000]
    previous_close = _parse_json_decimal_field(quote_context, "previousClose")
    if previous_close is None:
        previous_close = _parse_json_decimal_field(quote_context, "chartPreviousClose")
    change_percent = _calculate_change_percent(price, previous_close)

    name = preferred_name
    name_match = re.search(r'"name":"(?P<name>[^"]+)"', quote_context)
    if name is None and name_match is not None:
        name = _decode_json_string(name_match.group("name"))

    return StockQuote(
        stock_code=stock_code,
        name=name or stock_code,
        price=price,
        source=source,
        change_percent=change_percent,
    )


def _load_stock_list(urlopen) -> tuple[StockSearchMatch, ...]:
    global _STOCK_LIST_CACHE

    use_cache = urlopen is urllib.request.urlopen
    if use_cache and _STOCK_LIST_CACHE is not None:
        return _STOCK_LIST_CACHE

    matches: list[StockSearchMatch] = []
    for source, url, code_key, name_key, full_name_key in _STOCK_LIST_SOURCES:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept-Language": "zh-TW,zh;q=0.9",
            },
        )
        try:
            rows = _read_json(request, urlopen)
        except Exception:
            continue

        for row in rows:
            stock_code = str(row.get(code_key, "")).strip()
            name = str(row.get(name_key, "")).strip()
            full_name = str(row.get(full_name_key, "")).strip()
            if stock_code and name and stock_code.isdigit() and len(stock_code) == 4:
                matches.append(
                    StockSearchMatch(
                        stock_code=stock_code,
                        name=name,
                        source=source,
                        full_name=full_name,
                    )
                )

    if not matches:
        raise StockQuoteError("查不到股票名稱清單")

    stock_list = tuple(_unique_matches(matches))
    if use_cache:
        _STOCK_LIST_CACHE = stock_list
    return stock_list


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


def _parse_json_decimal_field(text: str, field_name: str) -> Decimal | None:
    match = re.search(rf'"{re.escape(field_name)}":(?P<value>-?\d+(?:\.\d+)?)', text)
    if match is None:
        return None
    return _parse_price(match.group("value"))


def _calculate_change_percent(price: Decimal, previous_close: Decimal | None) -> Decimal | None:
    if previous_close is None or previous_close == 0:
        return None
    return ((price - previous_close) / previous_close * Decimal("100")).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def _normalize_name(value: str) -> str:
    return re.sub(r"\s+", "", value).replace("臺", "台").lower()


def _unique_matches(matches: list[StockSearchMatch]) -> list[StockSearchMatch]:
    seen = set()
    unique = []
    for match in matches:
        if match.stock_code in seen:
            continue
        seen.add(match.stock_code)
        unique.append(match)
    return unique


def _decode_json_string(value: str) -> str:
    try:
        return json.loads(f'"{value}"')
    except json.JSONDecodeError:
        return value

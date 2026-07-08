import re
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from stock_fee_bot.quote import StockQuote, StockQuoteError, fetch_stock_quote


FEE_RATE = Decimal("0.001425")
DISCOUNT_RATE = Decimal("0.18")
MINIMUM_FEE = 20
SELL_TAX_RATE = Decimal("0.003")
PRICE_MATCH_TOLERANCE = Decimal("0.20")
ACCEPTED_MESSAGE_RE = re.compile(r"^\s*\d{4}(?:[\s,]+\d+(?:\.\d+)?){0,2}\s*$")


class InvalidMessageError(ValueError):
    """Raised when a user message cannot be parsed."""


@dataclass(frozen=True)
class ParsedInput:
    stock_code: str
    price: Decimal | None = None
    shares: int | None = None


@dataclass(frozen=True)
class TradeCost:
    price: Decimal
    shares: int
    trade_amount: int
    buy_fee: int
    sell_fee: int
    sell_tax: int
    buy_cost: int
    sell_cost: int
    total_cost: int


def parse_message(text: str) -> ParsedInput:
    if not ACCEPTED_MESSAGE_RE.fullmatch(text):
        raise InvalidMessageError("請只輸入數字：代號、代號 數字，或代號 股價 股數")

    numbers = re.findall(r"\d+(?:\.\d+)?", text.replace(",", " "))
    stock_code = numbers[0]
    if not stock_code.isdigit() or len(stock_code) != 4:
        raise InvalidMessageError("股票代號必須是 4 碼")

    if len(numbers) == 1:
        return ParsedInput(stock_code=stock_code)

    price = Decimal(numbers[1])
    if price <= 0:
        raise InvalidMessageError("股價或股數必須大於 0")

    if len(numbers) == 2:
        return ParsedInput(stock_code=stock_code, price=price)

    shares_decimal = Decimal(numbers[2])
    if shares_decimal <= 0 or shares_decimal != shares_decimal.to_integral_value():
        raise InvalidMessageError("股數必須是正整數")

    return ParsedInput(stock_code=stock_code, price=price, shares=int(shares_decimal))


def should_ignore_text(text: str) -> bool:
    return not ACCEPTED_MESSAGE_RE.fullmatch(text)


def calculate_trade_cost(price: float | Decimal, shares: int) -> TradeCost:
    price_decimal = Decimal(str(price))
    if price_decimal <= 0:
        raise ValueError("price must be greater than zero")
    if shares <= 0:
        raise ValueError("shares must be greater than zero")

    trade_amount_decimal = price_decimal * Decimal(shares)
    trade_amount = int(_round_ntd(trade_amount_decimal))
    buy_fee = _discounted_fee(trade_amount_decimal)
    sell_fee = _discounted_fee(trade_amount_decimal)
    sell_tax = int(_round_ntd(trade_amount_decimal * SELL_TAX_RATE))
    buy_cost = buy_fee
    sell_cost = sell_fee + sell_tax

    return TradeCost(
        price=price_decimal,
        shares=shares,
        trade_amount=trade_amount,
        buy_fee=buy_fee,
        sell_fee=sell_fee,
        sell_tax=sell_tax,
        buy_cost=buy_cost,
        sell_cost=sell_cost,
        total_cost=buy_cost + sell_cost,
    )


def suggest_minimum_shares(price: float | Decimal) -> int:
    price_decimal = Decimal(str(price))
    if price_decimal <= 0:
        raise ValueError("price must be greater than zero")

    shares = 1
    while _discounted_fee(price_decimal * Decimal(shares)) <= MINIMUM_FEE:
        shares += 1
    return shares


def format_reply(parsed: ParsedInput, quote_lookup=fetch_stock_quote) -> str:
    if parsed.price is not None and parsed.shares is not None:
        quote = _lookup_optional_quote(parsed.stock_code, quote_lookup)
        quote = StockQuote(
            stock_code=parsed.stock_code,
            name=quote.name if quote is not None else parsed.stock_code,
            price=parsed.price,
            source="User",
        )
        return format_trade_reply(quote, parsed.shares)

    try:
        quote = quote_lookup(parsed.stock_code)
    except StockQuoteError:
        return "\n".join(
            [
                f"{parsed.stock_code}",
                "查不到現價",
                "請確認股票代號，或稍後再試。",
            ]
        )

    if parsed.price is None:
        return format_quote_reply(quote)

    if _looks_like_market_price(parsed.price, quote.price):
        suggested_shares = suggest_minimum_shares(parsed.price)
        suggested_quote = StockQuote(
            stock_code=quote.stock_code,
            name=quote.name,
            price=parsed.price,
            source="User",
        )
        return format_suggestion_reply(suggested_quote, suggested_shares)

    if parsed.price != parsed.price.to_integral_value():
        raise InvalidMessageError("股數必須是正整數")

    return format_trade_reply(quote, int(parsed.price))


def format_quote_reply(quote: StockQuote) -> str:
    return "\n".join(
        [
            f"{quote.stock_code} {quote.name}",
            f"現價：{_format_price(quote.price)}元",
        ]
    )


def format_trade_reply(quote: StockQuote, shares: int) -> str:
    cost = calculate_trade_cost(quote.price, shares)
    return _format_trade_lines(quote.stock_code, quote.name, cost, f"股數：{cost.shares:,}股")


def format_suggestion_reply(quote: StockQuote, shares: int) -> str:
    cost = calculate_trade_cost(quote.price, shares)
    return _format_trade_lines(quote.stock_code, quote.name, cost, f"建議股數：{cost.shares:,}股")


def format_help() -> str:
    return "\n".join(
        [
            "請輸入：代號、代號 數字，或代號 股價 股數",
            "查現價：2330",
            "自動判斷股價/股數：2330 100",
            "直接試算：2330 2440 1000",
            "手續費折扣固定為 1.8 折。",
        ]
    )


def _format_trade_lines(stock_code: str, name: str, cost: TradeCost, share_line: str) -> str:
    return "\n".join(
        [
            f"{stock_code} {name}",
            f"現價：{_format_price(cost.price)}元",
            share_line,
            f"成交金額：{cost.trade_amount:,}元",
            f"買進成本：{cost.buy_cost:,}元",
            "---",
            f"賣出手續費：{cost.sell_fee:,}元",
            f"證交稅：{cost.sell_tax:,}元",
            f"賣出成本：{cost.sell_cost:,}元",
            "---",
            f"買賣合計成本：{cost.total_cost:,}元",
        ]
    )


def _lookup_optional_quote(stock_code: str, quote_lookup) -> StockQuote | None:
    try:
        return quote_lookup(stock_code)
    except StockQuoteError:
        return None


def _discounted_fee(trade_amount: Decimal) -> int:
    fee = _round_ntd(trade_amount * FEE_RATE * DISCOUNT_RATE)
    return max(MINIMUM_FEE, int(fee))


def _round_ntd(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def _format_price(value: Decimal) -> str:
    normalized = value.normalize()
    return f"{normalized:f}"


def _looks_like_market_price(candidate: Decimal, market_price: Decimal) -> bool:
    if market_price <= 0:
        return False
    return abs(candidate - market_price) / market_price <= PRICE_MATCH_TOLERANCE

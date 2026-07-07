import re
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP

from stock_fee_bot.quote import StockQuoteError, fetch_stock_quote


FEE_RATE = Decimal("0.001425")
SELL_TAX_RATE = Decimal("0.003")
MINIMUM_FEE = 20
DEFAULT_DISCOUNT = Decimal("0.18")
PRICE_CONFIRMATION_TOLERANCE = Decimal("0.20")


class InvalidMessageError(ValueError):
    """Raised when a user message cannot be parsed as a fee request."""


@dataclass(frozen=True)
class ParsedInput:
    stock_code: str
    price: Decimal | None = None
    shares: int | None = None
    discount: float = float(DEFAULT_DISCOUNT)


@dataclass(frozen=True)
class FeeResult:
    trade_amount: int
    standard_fee: int
    discounted_fee: int
    discount: float


@dataclass(frozen=True)
class RoundTripResult:
    trade_amount: int
    buy_fee: int
    sell_fee: int
    sell_tax: int
    total_cost: int
    discount: float


@dataclass(frozen=True)
class ShareSuggestion:
    price: Decimal
    shares: int
    trade_amount: int
    buy_fee: int
    sell_fee: int
    sell_tax: int
    total_cost: int
    discount: float


def calculate_fee(
    price: float | Decimal,
    shares: int,
    discount: float | Decimal = DEFAULT_DISCOUNT,
) -> FeeResult:
    price_decimal = Decimal(str(price))
    discount_decimal = Decimal(str(discount))

    if price_decimal <= 0:
        raise ValueError("price must be greater than zero")
    if shares <= 0:
        raise ValueError("shares must be greater than zero")
    if discount_decimal <= 0:
        raise ValueError("discount must be greater than zero")

    trade_amount_decimal = price_decimal * Decimal(shares)
    standard_fee = _apply_minimum_fee(trade_amount_decimal * FEE_RATE)
    discounted_fee = _apply_minimum_fee(Decimal(standard_fee) * discount_decimal)

    return FeeResult(
        trade_amount=int(_round_ntd(trade_amount_decimal)),
        standard_fee=standard_fee,
        discounted_fee=discounted_fee,
        discount=float(discount_decimal),
    )


def calculate_round_trip(
    price: float | Decimal,
    shares: int,
    discount: float | Decimal = DEFAULT_DISCOUNT,
) -> RoundTripResult:
    fee_result = calculate_fee(price, shares, discount)
    sell_tax = int(_round_ntd(Decimal(fee_result.trade_amount) * SELL_TAX_RATE))
    total_cost = fee_result.discounted_fee + fee_result.discounted_fee + sell_tax

    return RoundTripResult(
        trade_amount=fee_result.trade_amount,
        buy_fee=fee_result.discounted_fee,
        sell_fee=fee_result.discounted_fee,
        sell_tax=sell_tax,
        total_cost=total_cost,
        discount=fee_result.discount,
    )


def suggest_minimum_shares(
    price: float | Decimal,
    discount: float | Decimal = DEFAULT_DISCOUNT,
) -> ShareSuggestion:
    price_decimal = Decimal(str(price))
    discount_decimal = Decimal(str(discount))

    if price_decimal <= 0:
        raise ValueError("price must be greater than zero")
    if discount_decimal <= 0:
        raise ValueError("discount must be greater than zero")

    # To display a discounted fee above the 20 NTD minimum, the rounded
    # discounted fee must be at least 21 NTD.
    required_standard_fee = ((Decimal(MINIMUM_FEE) + Decimal("0.5")) / discount_decimal).to_integral_value(
        rounding=ROUND_CEILING
    )
    required_trade_amount = (required_standard_fee - Decimal("0.5")) / FEE_RATE
    shares = int((required_trade_amount / price_decimal).to_integral_value(rounding=ROUND_CEILING))

    while calculate_fee(price_decimal, shares, discount_decimal).discounted_fee <= MINIMUM_FEE:
        shares += 1
    while shares > 1 and calculate_fee(price_decimal, shares - 1, discount_decimal).discounted_fee > MINIMUM_FEE:
        shares -= 1

    round_trip = calculate_round_trip(price_decimal, shares, discount_decimal)
    return ShareSuggestion(
        price=price_decimal,
        shares=shares,
        trade_amount=round_trip.trade_amount,
        buy_fee=round_trip.buy_fee,
        sell_fee=round_trip.sell_fee,
        sell_tax=round_trip.sell_tax,
        total_cost=round_trip.total_cost,
        discount=round_trip.discount,
    )


def parse_message(text: str) -> ParsedInput:
    normalized = text.replace(",", " ").strip()
    numbers = re.findall(r"\d+(?:\.\d+)?", normalized)

    if len(numbers) == 1 and re.fullmatch(r"\d{4}", numbers[0]):
        return ParsedInput(stock_code=numbers[0])

    if len(numbers) < 2:
        raise InvalidMessageError("請輸入：代號，或代號 股價 股數（股數可省略）")

    stock_code = numbers[0].split(".")[0]
    price = Decimal(numbers[1])
    shares = int(Decimal(numbers[2])) if len(numbers) >= 3 else None

    if len(stock_code) != 4 or not stock_code.isdigit():
        raise InvalidMessageError("股票代號請輸入 4 碼")
    if price <= 0 or (shares is not None and shares <= 0):
        raise InvalidMessageError("股價與股數都必須大於 0")

    return ParsedInput(stock_code=stock_code, price=price, shares=shares, discount=float(DEFAULT_DISCOUNT))


def should_ignore_text(text: str) -> bool:
    return not re.search(r"\d", text)


def format_reply(parsed: ParsedInput, quote_lookup=fetch_stock_quote) -> str:
    if parsed.price is None:
        return _format_quote_reply(parsed.stock_code, quote_lookup)

    if parsed.shares is None:
        return _format_price_or_shares_reply(parsed, quote_lookup)

    round_trip = calculate_round_trip(parsed.price, parsed.shares, parsed.discount)
    discount_label = _format_discount_label(round_trip.discount)

    return "\n".join(
        [
            f"代號：{parsed.stock_code}",
            f"股價：{_format_decimal(parsed.price)} 元",
            f"股數：{parsed.shares:,} 股",
            f"成交金額：{round_trip.trade_amount:,} 元",
            "買進成本",
            f"買進手續費（{discount_label}）：{round_trip.buy_fee:,} 元",
            "---",
            "賣出成本",
            f"賣出手續費（{discount_label}）：{round_trip.sell_fee:,} 元",
            f"證交稅：{round_trip.sell_tax:,} 元",
            f"買賣合計成本：{round_trip.total_cost:,} 元",
        ]
    )


def _format_price_or_shares_reply(parsed: ParsedInput, quote_lookup) -> str:
    if parsed.price is None:
        return _format_quote_reply(parsed.stock_code, quote_lookup)

    try:
        quote = quote_lookup(parsed.stock_code)
    except StockQuoteError:
        return _format_suggestion_reply(parsed, suggest_minimum_shares(parsed.price, parsed.discount))

    if _looks_like_shares(parsed.price, quote.price):
        shares = int(parsed.price)
        return format_reply(
            ParsedInput(
                stock_code=parsed.stock_code,
                price=quote.price,
                shares=shares,
                discount=parsed.discount,
            ),
            quote_lookup=quote_lookup,
        )

    return _format_suggestion_reply(parsed, suggest_minimum_shares(parsed.price, parsed.discount))


def format_help() -> str:
    return "\n".join(
        [
            "請輸入：代號，或代號 股價 股數（股數可省略）",
            "查股價：2330",
            "建議股數：2330 950",
            "買賣試算：2330 950 1000",
            "目前手續費折扣固定為 1.8折。",
        ]
    )


def _format_quote_reply(stock_code: str, quote_lookup) -> str:
    try:
        quote = quote_lookup(stock_code)
    except StockQuoteError:
        return "\n".join(
            [
                f"代號：{stock_code}",
                "查不到目前股價。",
                "請確認代號是否正確，或稍後再試。",
            ]
        )

    return "\n".join(
        [
            f"代號：{quote.stock_code}",
            f"名稱：{quote.name}",
            f"目前股價：{_format_decimal(quote.price)} 元",
            f"資料來源：{quote.source}",
            "---",
            f"可輸入：{quote.stock_code} {_format_decimal(quote.price)}",
            f"或：{quote.stock_code} {_format_decimal(quote.price)} 1000",
        ]
    )


def _format_suggestion_reply(parsed: ParsedInput, suggestion: ShareSuggestion) -> str:
    discount_label = _format_discount_label(suggestion.discount)
    return "\n".join(
        [
            f"代號：{parsed.stock_code}",
            f"股價：{_format_decimal(suggestion.price)} 元",
            f"若要讓{discount_label}手續費超過 20 元低消：",
            f"至少 {suggestion.shares:,} 股",
            f"成交金額：約 {suggestion.trade_amount:,} 元",
            "買進成本",
            f"買進手續費（{discount_label}）：{suggestion.buy_fee:,} 元",
            "---",
            "賣出成本",
            f"賣出手續費（{discount_label}）：{suggestion.sell_fee:,} 元",
            f"賣出證交稅：約 {suggestion.sell_tax:,} 元",
            f"買賣合計成本：約 {suggestion.total_cost:,} 元",
        ]
    )


def _apply_minimum_fee(amount: Decimal) -> int:
    return max(MINIMUM_FEE, int(_round_ntd(amount)))


def _round_ntd(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def _format_discount_label(discount: float | Decimal) -> str:
    discount_decimal = Decimal(str(discount))
    folded = discount_decimal * Decimal("10")
    return f"{folded.normalize()}折"


def _format_decimal(value: Decimal) -> str:
    return f"{value.normalize():f}"


def _looks_like_shares(candidate: Decimal, market_price: Decimal) -> bool:
    if candidate != candidate.to_integral_value():
        return False

    difference_ratio = abs(candidate - market_price) / market_price
    return difference_ratio > PRICE_CONFIRMATION_TOLERANCE

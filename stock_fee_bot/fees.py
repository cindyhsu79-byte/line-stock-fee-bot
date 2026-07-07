import re
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP


FEE_RATE = Decimal("0.001425")
SELL_TAX_RATE = Decimal("0.003")
MINIMUM_FEE = 20
DEFAULT_DISCOUNT = Decimal("0.18")


class InvalidMessageError(ValueError):
    """Raised when a user message cannot be parsed as a fee request."""


@dataclass(frozen=True)
class ParsedInput:
    price: Decimal
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

    if len(numbers) < 1:
        raise InvalidMessageError("請輸入股價，或輸入股價與股數")

    price = Decimal(numbers[0])
    shares = int(Decimal(numbers[1])) if len(numbers) >= 2 else None
    discount = DEFAULT_DISCOUNT

    if len(numbers) >= 3:
        raw_discount = Decimal(numbers[2])
        discount = _normalize_discount(raw_discount, has_chinese_discount_marker="折" in normalized)

    if price <= 0 or (shares is not None and shares <= 0) or discount <= 0:
        raise InvalidMessageError("股價、股數、折扣都必須大於 0")

    return ParsedInput(price=price, shares=shares, discount=float(discount))


def format_reply(parsed: ParsedInput) -> str:
    if parsed.shares is None:
        return _format_suggestion_reply(suggest_minimum_shares(parsed.price, parsed.discount))

    round_trip = calculate_round_trip(parsed.price, parsed.shares, parsed.discount)
    discount_label = _format_discount_label(round_trip.discount)

    return "\n".join(
        [
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


def format_help() -> str:
    return "\n".join(
        [
            "請輸入股價，或輸入股價與股數。",
            "例如：50",
            "例如：50 1000",
            "目前手續費折扣預設固定為 1.8折。",
        ]
    )


def _format_suggestion_reply(suggestion: ShareSuggestion) -> str:
    discount_label = _format_discount_label(suggestion.discount)
    return "\n".join(
        [
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


def _normalize_discount(value: Decimal, has_chinese_discount_marker: bool) -> Decimal:
    if has_chinese_discount_marker or value > 1:
        return value / Decimal("10")
    return value


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

import re
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


FEE_RATE = Decimal("0.001425")
MINIMUM_FEE = 20


class InvalidMessageError(ValueError):
    """Raised when a user message cannot be parsed as a fee request."""


@dataclass(frozen=True)
class ParsedInput:
    price: Decimal
    shares: int
    discount: float = 1.0


@dataclass(frozen=True)
class FeeResult:
    trade_amount: int
    standard_fee: int
    discounted_fee: int
    discount: float


def calculate_fee(price: float | Decimal, shares: int, discount: float | Decimal = 1.0) -> FeeResult:
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


def parse_message(text: str) -> ParsedInput:
    normalized = text.replace(",", " ").strip()
    numbers = re.findall(r"\d+(?:\.\d+)?", normalized)

    if len(numbers) < 2:
        raise InvalidMessageError("請輸入股價與股數")

    price = Decimal(numbers[0])
    shares = int(Decimal(numbers[1]))
    discount = Decimal("1.0")

    if len(numbers) >= 3:
        raw_discount = Decimal(numbers[2])
        discount = _normalize_discount(raw_discount, has_chinese_discount_marker="折" in normalized)

    if price <= 0 or shares <= 0 or discount <= 0:
        raise InvalidMessageError("股價、股數、折扣都必須大於 0")

    return ParsedInput(price=price, shares=shares, discount=float(discount))


def format_reply(parsed: ParsedInput) -> str:
    result = calculate_fee(parsed.price, parsed.shares, parsed.discount)
    discount_label = _format_discount_label(result.discount)

    return "\n".join(
        [
            f"成交金額：{result.trade_amount:,} 元",
            f"原始手續費：{result.standard_fee:,} 元",
            f"{discount_label}後手續費：{result.discounted_fee:,} 元",
        ]
    )


def format_help() -> str:
    return "\n".join(
        [
            "請輸入：股價 股數 折扣",
            "例如：50 1000 6折",
            "也可以：股價50 股數1000 折扣6折",
            "不輸入折扣時會用原價手續費計算。",
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


def _format_discount_label(discount: Decimal) -> str:
    discount_decimal = Decimal(str(discount))
    if discount_decimal == Decimal("1.0") or discount_decimal == Decimal("1"):
        return "未折扣"

    folded = discount_decimal * Decimal("10")
    return f"{folded.normalize()}折"

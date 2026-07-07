import unittest

from stock_fee_bot.fees import (
    DEFAULT_DISCOUNT,
    InvalidMessageError,
    calculate_fee,
    calculate_round_trip,
    format_help,
    format_reply,
    parse_message,
    suggest_minimum_shares,
)


class FeeCalculationTest(unittest.TestCase):
    def test_calculates_standard_and_discounted_fee(self):
        result = calculate_fee(price=50, shares=1000, discount=0.18)

        self.assertEqual(result.trade_amount, 50000)
        self.assertEqual(result.standard_fee, 71)
        self.assertEqual(result.discounted_fee, 20)
        self.assertEqual(result.discount, 0.18)

    def test_applies_minimum_fee_to_standard_and_discounted_fee(self):
        result = calculate_fee(price=10, shares=100, discount=0.18)

        self.assertEqual(result.trade_amount, 1000)
        self.assertEqual(result.standard_fee, 20)
        self.assertEqual(result.discounted_fee, 20)

    def test_calculates_round_trip_costs(self):
        result = calculate_round_trip(price=50, shares=1000, discount=0.18)

        self.assertEqual(result.buy_fee, 20)
        self.assertEqual(result.sell_fee, 20)
        self.assertEqual(result.sell_tax, 150)
        self.assertEqual(result.total_cost, 190)

    def test_rejects_non_positive_values(self):
        with self.assertRaises(ValueError):
            calculate_fee(price=0, shares=1000, discount=0.18)

        with self.assertRaises(ValueError):
            calculate_fee(price=50, shares=0, discount=0.18)

        with self.assertRaises(ValueError):
            calculate_fee(price=50, shares=1000, discount=0)


class SuggestionTest(unittest.TestCase):
    def test_suggests_shares_that_make_discounted_fee_exceed_minimum(self):
        suggestion = suggest_minimum_shares(price=50, discount=DEFAULT_DISCOUNT)

        self.assertEqual(suggestion.shares, 1593)
        self.assertEqual(suggestion.trade_amount, 79650)
        self.assertEqual(suggestion.buy_fee, 21)
        self.assertEqual(suggestion.sell_fee, 21)
        self.assertGreater(suggestion.buy_fee, 20)


class MessageParsingTest(unittest.TestCase):
    def test_parses_price_only_as_suggestion_request(self):
        parsed = parse_message("50")

        self.assertEqual(parsed.price, 50)
        self.assertIsNone(parsed.shares)
        self.assertEqual(parsed.discount, 0.18)

    def test_parses_plain_numbers_with_default_discount(self):
        parsed = parse_message("50 1000")

        self.assertEqual(parsed.price, 50)
        self.assertEqual(parsed.shares, 1000)
        self.assertEqual(parsed.discount, 0.18)

    def test_still_accepts_explicit_chinese_discount(self):
        parsed = parse_message("50 1000 6折")

        self.assertEqual(parsed.price, 50)
        self.assertEqual(parsed.shares, 1000)
        self.assertEqual(parsed.discount, 0.6)

    def test_parses_labeled_input(self):
        parsed = parse_message("股價50 股數1000")

        self.assertEqual(parsed.price, 50)
        self.assertEqual(parsed.shares, 1000)
        self.assertEqual(parsed.discount, 0.18)

    def test_rejects_invalid_message(self):
        with self.assertRaises(InvalidMessageError):
            parse_message("幫我算一下")


class ReplyFormattingTest(unittest.TestCase):
    def test_formats_round_trip_reply_for_line(self):
        reply = format_reply(parse_message("50 1000"))

        self.assertIn("成交金額：50,000 元", reply)
        self.assertIn("買進成本", reply)
        self.assertIn("買進手續費（1.8折）：20 元", reply)
        self.assertIn("---", reply)
        self.assertIn("賣出成本", reply)
        self.assertIn("賣出手續費（1.8折）：20 元", reply)
        self.assertIn("證交稅：150 元", reply)
        self.assertIn("買賣合計成本：190 元", reply)

    def test_formats_price_only_suggestion_reply(self):
        reply = format_reply(parse_message("50"))

        self.assertIn("股價：50 元", reply)
        self.assertIn("至少 1,593 股", reply)
        self.assertIn("買進成本", reply)
        self.assertIn("買進手續費（1.8折）：21 元", reply)
        self.assertIn("---", reply)
        self.assertIn("賣出成本", reply)
        self.assertIn("賣出手續費（1.8折）：21 元", reply)

    def test_help_includes_examples(self):
        help_text = format_help()

        self.assertIn("50", help_text)
        self.assertIn("50 1000", help_text)


if __name__ == "__main__":
    unittest.main()

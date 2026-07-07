import unittest

from stock_fee_bot.fees import (
    InvalidMessageError,
    calculate_fee,
    format_help,
    format_reply,
    parse_message,
)


class FeeCalculationTest(unittest.TestCase):
    def test_calculates_standard_and_discounted_fee(self):
        result = calculate_fee(price=50, shares=1000, discount=0.6)

        self.assertEqual(result.trade_amount, 50000)
        self.assertEqual(result.standard_fee, 71)
        self.assertEqual(result.discounted_fee, 43)
        self.assertEqual(result.discount, 0.6)

    def test_applies_minimum_fee_to_standard_and_discounted_fee(self):
        result = calculate_fee(price=10, shares=100, discount=0.1)

        self.assertEqual(result.trade_amount, 1000)
        self.assertEqual(result.standard_fee, 20)
        self.assertEqual(result.discounted_fee, 20)

    def test_rejects_non_positive_values(self):
        with self.assertRaises(ValueError):
            calculate_fee(price=0, shares=1000, discount=0.6)

        with self.assertRaises(ValueError):
            calculate_fee(price=50, shares=0, discount=0.6)

        with self.assertRaises(ValueError):
            calculate_fee(price=50, shares=1000, discount=0)


class MessageParsingTest(unittest.TestCase):
    def test_parses_plain_numbers_with_chinese_discount(self):
        parsed = parse_message("50 1000 6折")

        self.assertEqual(parsed.price, 50)
        self.assertEqual(parsed.shares, 1000)
        self.assertEqual(parsed.discount, 0.6)

    def test_parses_labeled_input(self):
        parsed = parse_message("股價50 股數1000 折扣6折")

        self.assertEqual(parsed.price, 50)
        self.assertEqual(parsed.shares, 1000)
        self.assertEqual(parsed.discount, 0.6)

    def test_parses_decimal_discount(self):
        parsed = parse_message("50, 1000, 0.6")

        self.assertEqual(parsed.price, 50)
        self.assertEqual(parsed.shares, 1000)
        self.assertEqual(parsed.discount, 0.6)

    def test_defaults_to_no_discount(self):
        parsed = parse_message("50 1000")

        self.assertEqual(parsed.price, 50)
        self.assertEqual(parsed.shares, 1000)
        self.assertEqual(parsed.discount, 1.0)

    def test_rejects_invalid_message(self):
        with self.assertRaises(InvalidMessageError):
            parse_message("幫我算一下")


class ReplyFormattingTest(unittest.TestCase):
    def test_formats_reply_for_line(self):
        reply = format_reply(parse_message("50 1000 6折"))

        self.assertIn("成交金額：50,000 元", reply)
        self.assertIn("原始手續費：71 元", reply)
        self.assertIn("6折後手續費：43 元", reply)

    def test_help_includes_examples(self):
        help_text = format_help()

        self.assertIn("50 1000 6折", help_text)
        self.assertIn("股價50 股數1000 折扣6折", help_text)


if __name__ == "__main__":
    unittest.main()

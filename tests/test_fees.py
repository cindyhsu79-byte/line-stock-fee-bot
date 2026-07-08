import unittest
from decimal import Decimal

from stock_fee_bot.fees import (
    InvalidMessageError,
    calculate_trade_cost,
    format_help,
    format_reply,
    parse_message,
    should_ignore_text,
)
from stock_fee_bot.quote import StockQuote, StockQuoteError


def quote_not_available(stock_code):
    raise StockQuoteError(stock_code)


class MessageParsingTest(unittest.TestCase):
    def test_parses_four_digit_code_as_quote_request(self):
        parsed = parse_message("2330")

        self.assertEqual(parsed.stock_code, "2330")
        self.assertIsNone(parsed.shares)

    def test_parses_code_and_shares_as_trade_request(self):
        parsed = parse_message("2330 1000")

        self.assertEqual(parsed.stock_code, "2330")
        self.assertEqual(parsed.shares, 1000)

    def test_rejects_price_style_input(self):
        with self.assertRaises(InvalidMessageError):
            parse_message("2330 2440 1000")

    def test_rejects_non_integer_shares(self):
        with self.assertRaises(InvalidMessageError):
            parse_message("2330 100.5")

    def test_rejects_invalid_message(self):
        with self.assertRaises(InvalidMessageError):
            parse_message("hello")


class ChatIgnoreTest(unittest.TestCase):
    def test_ignores_plain_chat_text(self):
        self.assertTrue(should_ignore_text("hello"))
        self.assertTrue(should_ignore_text("真厲害"))
        self.assertTrue(should_ignore_text("請查 2330"))
        self.assertTrue(should_ignore_text("2330 股"))
        self.assertTrue(should_ignore_text("2330 abc"))
        self.assertFalse(should_ignore_text("2330"))
        self.assertFalse(should_ignore_text("2330 1000"))
        self.assertFalse(should_ignore_text("2330,1000"))


class FeeCalculationTest(unittest.TestCase):
    def test_calculates_minimum_fee_and_sell_tax(self):
        cost = calculate_trade_cost(price=50, shares=1000)

        self.assertEqual(cost.trade_amount, 50000)
        self.assertEqual(cost.buy_fee, 20)
        self.assertEqual(cost.sell_fee, 20)
        self.assertEqual(cost.sell_tax, 150)
        self.assertEqual(cost.buy_cost, 20)
        self.assertEqual(cost.sell_cost, 170)
        self.assertEqual(cost.total_cost, 190)

    def test_calculates_discounted_fee_above_minimum(self):
        cost = calculate_trade_cost(price=2440, shares=1000)

        self.assertEqual(cost.trade_amount, 2440000)
        self.assertEqual(cost.buy_fee, 626)
        self.assertEqual(cost.sell_fee, 626)
        self.assertEqual(cost.sell_tax, 7320)
        self.assertEqual(cost.sell_cost, 7946)
        self.assertEqual(cost.total_cost, 8572)

    def test_rejects_non_positive_values(self):
        with self.assertRaises(ValueError):
            calculate_trade_cost(price=0, shares=1000)
        with self.assertRaises(ValueError):
            calculate_trade_cost(price=50, shares=0)


class ReplyFormattingTest(unittest.TestCase):
    def test_formats_quote_reply_with_current_price_only(self):
        def fake_lookup(stock_code):
            self.assertEqual(stock_code, "2330")
            return StockQuote(stock_code="2330", name="台積電", price=Decimal("950"), source="TWSE")

        reply = format_reply(parse_message("2330"), quote_lookup=fake_lookup)

        self.assertEqual(reply, "2330 台積電\n現價：950元")
        self.assertNotIn("漲跌", reply)
        self.assertNotIn("TWSE", reply)
        self.assertNotIn("---", reply)

    def test_formats_trade_reply_for_line(self):
        def fake_lookup(stock_code):
            self.assertEqual(stock_code, "2330")
            return StockQuote(stock_code="2330", name="台積電", price=Decimal("2440"), source="TWSE")

        reply = format_reply(parse_message("2330 1000"), quote_lookup=fake_lookup)

        self.assertIn("2330 台積電", reply)
        self.assertIn("現價：2440元", reply)
        self.assertIn("股數：1,000股", reply)
        self.assertIn("成交金額：2,440,000元", reply)
        self.assertIn("買進成本：626元", reply)
        self.assertIn("賣出手續費：626元", reply)
        self.assertIn("證交稅：7,320元", reply)
        self.assertIn("賣出成本：7,946元", reply)
        self.assertIn("買賣合計成本：8,572元", reply)
        self.assertEqual(reply.count("---"), 2)

    def test_formats_quote_error(self):
        reply = format_reply(parse_message("9999"), quote_lookup=quote_not_available)

        self.assertIn("9999", reply)
        self.assertIn("查不到現價", reply)

    def test_help_includes_examples(self):
        help_text = format_help()

        self.assertIn("2330", help_text)
        self.assertIn("2330 1000", help_text)
        self.assertIn("1.8 折", help_text)


if __name__ == "__main__":
    unittest.main()

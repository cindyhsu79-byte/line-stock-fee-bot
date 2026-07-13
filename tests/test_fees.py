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
from stock_fee_bot.quote import StockQuote, StockQuoteError, StockSearchMatch


def quote_not_available(stock_code):
    raise StockQuoteError(stock_code)


class MessageParsingTest(unittest.TestCase):
    def test_parses_four_digit_code_as_quote_request(self):
        parsed = parse_message("2330")

        self.assertEqual(parsed.stock_code, "2330")
        self.assertIsNone(parsed.price)
        self.assertIsNone(parsed.shares)

    def test_parses_code_and_one_number_as_ambiguous_request(self):
        parsed = parse_message("2330 100")

        self.assertEqual(parsed.stock_code, "2330")
        self.assertEqual(parsed.price, Decimal("100"))
        self.assertIsNone(parsed.shares)

    def test_parses_code_price_and_shares(self):
        parsed = parse_message("2330 2440 1000")

        self.assertEqual(parsed.stock_code, "2330")
        self.assertEqual(parsed.price, Decimal("2440"))
        self.assertEqual(parsed.shares, 1000)

    def test_rejects_non_integer_explicit_shares(self):
        with self.assertRaises(InvalidMessageError):
            parse_message("2330 2440 100.5")

    def test_rejects_invalid_message(self):
        with self.assertRaises(InvalidMessageError):
            parse_message("hello")

    def test_parses_stock_name_query(self):
        parsed = parse_message("台積")

        self.assertIsNone(parsed.stock_code)
        self.assertEqual(parsed.stock_query, "台積")
        self.assertIsNone(parsed.price)
        self.assertIsNone(parsed.shares)


class ChatIgnoreTest(unittest.TestCase):
    def test_ignores_text_mixed_with_numbers(self):
        def no_matches(query):
            return []

        self.assertTrue(should_ignore_text("hello"))
        self.assertTrue(should_ignore_text("真厲害", stock_search=no_matches))
        self.assertTrue(should_ignore_text("請查 2330"))
        self.assertTrue(should_ignore_text("2330 股"))
        self.assertTrue(should_ignore_text("2330 abc"))
        self.assertFalse(should_ignore_text("2330"))
        self.assertFalse(should_ignore_text("2330 100"))
        self.assertFalse(should_ignore_text("2330 2440 1000"))
        self.assertFalse(should_ignore_text("2330,1000"))

    def test_accepts_stock_name_only_when_it_matches_a_stock(self):
        def one_match(query):
            return [StockSearchMatch(stock_code="2330", name="台積電", source="TWSE")]

        self.assertFalse(should_ignore_text("台積", stock_search=one_match))


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


class ReplyFormattingTest(unittest.TestCase):
    def test_formats_quote_reply_with_current_price_only(self):
        def fake_lookup(stock_code):
            self.assertEqual(stock_code, "2330")
            return StockQuote(
                stock_code="2330",
                name="台積電",
                price=Decimal("2440"),
                source="Yahoo TW",
                change_percent=Decimal("1.04"),
            )

        reply = format_reply(parse_message("2330"), quote_lookup=fake_lookup)

        self.assertEqual(reply, "2330 台積電\n現價：2440元 +1.04%")
        self.assertNotIn("Yahoo", reply)
        self.assertNotIn("---", reply)

    def test_formats_quote_reply_from_partial_stock_name(self):
        def fake_search(query):
            self.assertEqual(query, "台積")
            return [StockSearchMatch(stock_code="2330", name="台積電", source="TWSE")]

        def fake_lookup(stock_code):
            self.assertEqual(stock_code, "2330")
            return StockQuote(
                stock_code="2330",
                name="台積電",
                price=Decimal("2440"),
                source="Yahoo TW",
                change_percent=Decimal("1.04"),
            )

        reply = format_reply(
            parse_message("台積"),
            quote_lookup=fake_lookup,
            stock_search=fake_search,
        )

        self.assertEqual(reply, "2330 台積電\n現價：2440元 +1.04%")

    def test_formats_multiple_name_matches(self):
        def fake_search(query):
            return [
                StockSearchMatch(stock_code="2330", name="台積電", source="TWSE"),
                StockSearchMatch(stock_code="6770", name="力積電", source="TWSE"),
            ]

        reply = format_reply(parse_message("積電"), stock_search=fake_search)

        self.assertEqual(
            reply,
            "找到多個股票，請輸入代號：\n2330 台積電\n6770 力積電",
        )

    def test_treats_second_number_as_shares_when_far_from_market_price(self):
        def fake_lookup(stock_code):
            return StockQuote(stock_code="2330", name="台積電", price=Decimal("2440"), source="Yahoo TW")

        reply = format_reply(parse_message("2330 100"), quote_lookup=fake_lookup)

        self.assertIn("現價：2440元", reply)
        self.assertIn("股數：100股", reply)
        self.assertIn("成交金額：244,000元", reply)
        self.assertIn("買賣合計成本：858元", reply)

    def test_treats_second_number_as_price_when_close_to_market_price(self):
        def fake_lookup(stock_code):
            return StockQuote(stock_code="2330", name="台積電", price=Decimal("2440"), source="Yahoo TW")

        reply = format_reply(parse_message("2330 2440"), quote_lookup=fake_lookup)

        self.assertIn("現價：2440元", reply)
        self.assertIn("建議股數：33股", reply)
        self.assertIn("成交金額：80,520元", reply)

    def test_uses_explicit_price_and_shares_without_market_price(self):
        reply = format_reply(parse_message("2330 2440 1000"), quote_lookup=quote_not_available)

        self.assertIn("2330", reply)
        self.assertIn("現價：2440元", reply)
        self.assertIn("股數：1,000股", reply)
        self.assertIn("成交金額：2,440,000元", reply)
        self.assertIn("買賣合計成本：8,572元", reply)

    def test_formats_quote_error(self):
        reply = format_reply(parse_message("9999"), quote_lookup=quote_not_available)

        self.assertIn("9999", reply)
        self.assertIn("查不到現價", reply)

    def test_help_includes_examples(self):
        help_text = format_help()

        self.assertIn("2330", help_text)
        self.assertIn("2330 100", help_text)
        self.assertIn("2330 2440 1000", help_text)


if __name__ == "__main__":
    unittest.main()

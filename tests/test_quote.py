import json
import unittest
from decimal import Decimal

from stock_fee_bot.quote import StockQuoteError, fetch_stock_quote


class QuoteLookupTest(unittest.TestCase):
    def test_uses_yahoo_tw_page_price_with_twse_name(self):
        responses = [
            {"msgArray": [{"c": "2330", "n": "台積電", "z": "950.00"}]},
            '"symbol":"2330.TW","name":"台積電","regularMarketTime":1783477740,"regularMarketPrice":2445,"chartPreviousClose":2440',
        ]

        def fake_urlopen(request, timeout):
            return FakeResponse(responses.pop(0))

        quote = fetch_stock_quote("2330", urlopen=fake_urlopen)

        self.assertEqual(quote.stock_code, "2330")
        self.assertEqual(quote.name, "台積電")
        self.assertEqual(quote.price, Decimal("2445"))
        self.assertEqual(quote.source, "Yahoo TW")

    def test_uses_yahoo_two_for_otc_stock(self):
        responses = [
            {"msgArray": []},
            {"msgArray": [{"c": "1234", "n": "上櫃公司", "z": "12.35"}]},
            'no price here',
            '"symbol":"1234.TWO","name":"上櫃公司","regularMarketPrice":13.4',
        ]

        def fake_urlopen(request, timeout):
            return FakeResponse(responses.pop(0))

        quote = fetch_stock_quote("1234", urlopen=fake_urlopen)

        self.assertEqual(quote.name, "上櫃公司")
        self.assertEqual(quote.price, Decimal("13.4"))
        self.assertEqual(quote.source, "Yahoo TWO")

    def test_uses_yahoo_name_when_market_name_is_not_available(self):
        responses = [
            {"msgArray": []},
            {"msgArray": []},
            '"symbol":"2330.TW","name":"台積電","regularMarketPrice":950.5',
        ]

        def fake_urlopen(request, timeout):
            return FakeResponse(responses.pop(0))

        quote = fetch_stock_quote("2330", urlopen=fake_urlopen)

        self.assertEqual(quote.name, "台積電")
        self.assertEqual(quote.price, Decimal("950.5"))
        self.assertEqual(quote.source, "Yahoo TW")

    def test_raises_when_yahoo_has_no_price(self):
        responses = [
            {"msgArray": [{"c": "2330", "n": "台積電", "z": "950.00"}]},
            '"symbol":"2330.TW","name":"台積電","chartPreviousClose":2440',
            '"symbol":"2330.TWO","name":"台積電","chartPreviousClose":2440',
        ]

        def fake_urlopen(request, timeout):
            return FakeResponse(responses.pop(0))

        with self.assertRaises(StockQuoteError):
            fetch_stock_quote("2330", urlopen=fake_urlopen)

    def test_rejects_invalid_stock_code(self):
        with self.assertRaises(StockQuoteError):
            fetch_stock_quote("台積電")


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        if isinstance(self.payload, str):
            return self.payload.encode("utf-8")
        return json.dumps(self.payload).encode("utf-8")


if __name__ == "__main__":
    unittest.main()

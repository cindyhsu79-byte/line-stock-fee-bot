import json
import unittest
from decimal import Decimal

from stock_fee_bot.quote import StockQuoteError, fetch_stock_quote


class QuoteLookupTest(unittest.TestCase):
    def test_fetches_twse_quote_from_json_payload(self):
        payload = {
            "msgArray": [
                {
                    "c": "2330",
                    "n": "台積電",
                    "z": "950.00",
                }
            ]
        }

        def fake_urlopen(request, timeout):
            return FakeResponse(payload)

        quote = fetch_stock_quote("2330", urlopen=fake_urlopen)

        self.assertEqual(quote.stock_code, "2330")
        self.assertEqual(quote.name, "台積電")
        self.assertEqual(quote.price, Decimal("950.00"))
        self.assertEqual(quote.source, "TWSE")

    def test_tries_otc_when_twse_has_no_price(self):
        responses = [
            {"msgArray": [{"c": "1234", "n": "上市測試", "z": "-"}]},
            {"msgArray": [{"c": "1234", "n": "上櫃測試", "z": "12.35"}]},
        ]

        def fake_urlopen(request, timeout):
            return FakeResponse(responses.pop(0))

        quote = fetch_stock_quote("1234", urlopen=fake_urlopen)

        self.assertEqual(quote.name, "上櫃測試")
        self.assertEqual(quote.price, Decimal("12.35"))
        self.assertEqual(quote.source, "TPEx")

    def test_tries_yahoo_when_twse_and_otc_have_no_price(self):
        responses = [
            {"msgArray": []},
            {"msgArray": []},
            {"chart": {"result": [{"meta": {"regularMarketPrice": 950.5, "shortName": "TSMC"}}]}},
        ]

        def fake_urlopen(request, timeout):
            return FakeResponse(responses.pop(0))

        quote = fetch_stock_quote("2330", urlopen=fake_urlopen)

        self.assertEqual(quote.stock_code, "2330")
        self.assertEqual(quote.name, "TSMC")
        self.assertEqual(quote.price, Decimal("950.5"))
        self.assertEqual(quote.source, "Yahoo TW")

    def test_raises_when_no_price_is_available(self):
        def fake_urlopen(request, timeout):
            return FakeResponse({"msgArray": []})

        with self.assertRaises(StockQuoteError):
            fetch_stock_quote("9999", urlopen=fake_urlopen)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")

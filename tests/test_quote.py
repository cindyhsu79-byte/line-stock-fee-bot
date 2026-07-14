import json
import unittest
from decimal import Decimal

from stock_fee_bot.quote import StockQuoteError, fetch_index_quote, fetch_stock_quote, search_stock_matches


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
        self.assertEqual(quote.change_percent, Decimal("0.20"))
        self.assertEqual(quote.quote_type, "EQUITY")
        self.assertEqual(quote.source, "Yahoo TW")

    def test_uses_yahoo_tw_page_for_etf_code(self):
        responses = [
            '"symbol":"00878.TW","name":"國泰永續高股息","quoteType":"ETF","regularMarketPrice":32.27,"previousClose":33.13',
        ]

        def fake_urlopen(request, timeout):
            return FakeResponse(responses.pop(0))

        quote = fetch_stock_quote("00878", urlopen=fake_urlopen)

        self.assertEqual(quote.stock_code, "00878")
        self.assertEqual(quote.name, "國泰永續高股息")
        self.assertEqual(quote.price, Decimal("32.27"))
        self.assertEqual(quote.change_percent, Decimal("-2.60"))
        self.assertEqual(quote.quote_type, "ETF")

    def test_fetches_weighted_index_quote(self):
        responses = [
            '"symbol":"^TWII","name":"加權指數","quoteType":"INDEX","regularMarketPrice":44014.56,"previousClose":45380.52',
        ]

        def fake_urlopen(request, timeout):
            return FakeResponse(responses.pop(0))

        quote = fetch_index_quote("加權", urlopen=fake_urlopen)

        self.assertEqual(quote.stock_code, "")
        self.assertEqual(quote.name, "加權指數")
        self.assertEqual(quote.price, Decimal("44014.56"))
        self.assertEqual(quote.change_percent, Decimal("-3.01"))
        self.assertEqual(quote.quote_type, "INDEX")

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

    def test_searches_stock_by_partial_name(self):
        responses = [
            [],
            [],
            [
                {
                    "公司代號": "2330",
                    "公司簡稱": "台積電",
                    "公司名稱": "台灣積體電路製造股份有限公司",
                },
                {
                    "公司代號": "6770",
                    "公司簡稱": "力積電",
                    "公司名稱": "力晶積成電子製造股份有限公司",
                },
            ],
            [],
        ]

        def fake_urlopen(request, timeout):
            return FakeResponse(responses.pop(0))

        matches = search_stock_matches("台積", urlopen=fake_urlopen)

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].stock_code, "2330")
        self.assertEqual(matches[0].name, "台積電")

    def test_search_normalizes_tai_character(self):
        responses = [
            [],
            [],
            [
                {
                    "公司代號": "2330",
                    "公司簡稱": "臺積電",
                    "公司名稱": "臺灣積體電路製造股份有限公司",
                }
            ],
            [],
        ]

        def fake_urlopen(request, timeout):
            return FakeResponse(responses.pop(0))

        matches = search_stock_matches("台積", urlopen=fake_urlopen)

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].stock_code, "2330")
        self.assertEqual(matches[0].name, "臺積電")

    def test_search_returns_multiple_close_matches(self):
        responses = [
            [],
            [],
            [
                {
                    "公司代號": "2330",
                    "公司簡稱": "台積電",
                    "公司名稱": "台灣積體電路製造股份有限公司",
                },
                {
                    "公司代號": "6770",
                    "公司簡稱": "力積電",
                    "公司名稱": "力晶積成電子製造股份有限公司",
                },
            ],
            [],
        ]

        def fake_urlopen(request, timeout):
            return FakeResponse(responses.pop(0))

        matches = search_stock_matches("積電", urlopen=fake_urlopen)

        self.assertEqual([match.stock_code for match in matches], ["2330", "6770"])

    def test_searches_etf_by_partial_name(self):
        responses = [
            [
                {
                    "Code": "00878",
                    "Name": "國泰永續高股息",
                },
                {
                    "Code": "006208",
                    "Name": "富邦台50",
                },
            ],
            [],
            [],
            [],
        ]

        def fake_urlopen(request, timeout):
            return FakeResponse(responses.pop(0))

        matches = search_stock_matches("高股息", urlopen=fake_urlopen)

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].stock_code, "00878")
        self.assertEqual(matches[0].name, "國泰永續高股息")


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

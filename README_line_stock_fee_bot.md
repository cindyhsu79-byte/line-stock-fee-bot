# LINE 股票小幫手

這是一個自己使用的 LINE 小工具。輸入台股代號和股數後，小幫手會抓現價並回覆買進成本、賣出成本與買賣合計成本。

## 使用方式

```text
2330
```

回覆現價：

```text
2330 台積電
現價：2440元 +1.04%
```

也可以輸入股票名稱或部分名稱：

```text
台積
```

回覆：

```text
2330 台積電
現價：2440元 +1.04%
```

```text
2330 1000
```

回覆買賣試算：

```text
2330 台積電
現價：2440元 +1.04%
股數：1,000股
成交金額：2,440,000元
買進成本：626元
---
賣出手續費：626元
證交稅：7,320元
賣出成本：7,946元
---
買賣合計成本：8,572元
```

## 計算規則

- 手續費率：0.1425%
- 手續費折扣：固定 1.8 折
- 折扣後手續費最低：20 元
- 證交稅：賣出成交金額的 0.3%
- 金額四捨五入到整數新台幣

## LINE 設定

Render 環境變數需要填：

```text
LINE_CHANNEL_SECRET
LINE_CHANNEL_ACCESS_TOKEN
```

LINE Developers 的 Webhook URL：

```text
https://line-stock-fee-bot.onrender.com/callback
```

## 本機測試

```powershell
python -m unittest discover -s tests -p "test*.py"
python -m py_compile stock_fee_bot/quote.py stock_fee_bot/fees.py stock_fee_bot/line_app.py run_line_bot.py
```

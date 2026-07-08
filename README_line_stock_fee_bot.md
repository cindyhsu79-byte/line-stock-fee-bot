# LINE 股票小幫手

這是一個自己使用的 LINE 小工具。輸入台股代號和股數後，小幫手會抓現價並回覆買進成本、賣出成本與買賣合計成本。

## 使用方式

```text
2330
```

回覆現價：

```text
2330 台積電
現價：2440元
```

```text
2330 1000
```

回覆買賣試算：

```text
2330 台積電
現價：2440元
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
# LINE 台股手續費機器人

這是一版小型原型：你在 LINE 傳股價、股數、折扣，機器人回覆原始手續費與折扣後手續費。

## 可輸入的格式

```text
50 1000
50 1000 6折
股價50 股數1000 折扣6折
50, 1000, 0.6
```

## 計算規則

- 成交金額 = 股價 * 股數
- 原始手續費 = 成交金額 * 0.1425%
- 手續費四捨五入到整數元
- 最低手續費 20 元
- 折扣後手續費也套用最低 20 元

## 本機先試算

```powershell
python -m unittest discover -s tests -p "test*.py"
python -c "from stock_fee_bot.fees import parse_message, format_reply; print(format_reply(parse_message('50 1000 6折')))"
```

## 啟動 webhook

```powershell
python run_line_bot.py
```

啟動後會有：

- 健康檢查：`GET /health`
- LINE webhook：`POST /callback`

## 接到 LINE

1. 在 LINE Developers 建立 Messaging API channel。
2. 把 `.env.example` 的值設成系統環境變數。
3. 將服務部署到有 HTTPS 的主機。
4. 在 LINE Developers 的 Webhook URL 填：

```text
https://你的網域/callback
```

如果沒有設定 `LINE_CHANNEL_ACCESS_TOKEN`，程式會把要回覆的文字印在終端機，方便本機測試。

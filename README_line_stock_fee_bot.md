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

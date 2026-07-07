# LINE 台股手續費機器人部署白話指南

這份是給第一次設定 LINE Bot 的版本。你不用理解所有技術名詞，照順序做就好。

## 你要準備的帳號

1. LINE 帳號
2. LINE Official Account / LINE Developers 帳號
3. GitHub 帳號
4. Render 帳號

## 第一段：建立 LINE 官方帳號和 Messaging API Channel

1. 打開 LINE Official Account Manager：`https://manager.line.biz/`
2. 用你的 LINE 帳號登入。
3. 建立一個官方帳號，例如名稱填「台股手續費小幫手」。
4. 建好後，進入該官方帳號後台。
5. 找到 Messaging API 相關設定，啟用 Messaging API。
6. 啟用時會要求選 Provider。第一次做可以建立一個新的 Provider，例如「個人工具」。
7. 啟用後，系統會幫你建立 Messaging API channel。

注意：現在 LINE 不再讓你直接從 LINE Developers 建立 Messaging API channel，必須先透過 LINE Official Account 啟用 Messaging API。

## 第二段：找到 LINE_CHANNEL_SECRET

1. 打開 LINE Developers Console：`https://developers.line.biz/console/`
2. 選剛剛的 Provider。
3. 點進剛剛建立的 Messaging API channel。
4. 在 Basic settings 分頁找 `Channel secret`。
5. 這串值就是要填到部署平台的：

```text
LINE_CHANNEL_SECRET
```

不要把這串貼給別人，也不要公開放在 GitHub。

## 第三段：找到 LINE_CHANNEL_ACCESS_TOKEN

1. 在同一個 Messaging API channel 裡，切到 Messaging API 分頁。
2. 找 `Channel access token`。
3. 如果還沒有 token，按 Issue 或 Generate。
4. 複製產生的 token。
5. 這串值就是要填到部署平台的：

```text
LINE_CHANNEL_ACCESS_TOKEN
```

不要把這串貼給別人，也不要公開放在 GitHub。

## 第四段：把程式放到 GitHub

因為 Render 通常從 GitHub 抓程式部署，所以要先把這個資料夾放到 GitHub repo。

最簡單做法：

1. 到 `https://github.com/` 建立一個新的 repository。
2. 名稱可以叫 `line-stock-fee-bot`。
3. 不要公開你的 secret/token。
4. 把這個專案資料夾上傳到 GitHub。

如果你不熟 GitHub Desktop，可以用 GitHub 網站的 Add file 上傳檔案，但資料夾多時會比較麻煩。

## 第五段：用 Render 部署

1. 打開 Render：`https://dashboard.render.com/`
2. 建立 New > Web Service。
3. 連接 GitHub，選 `line-stock-fee-bot` 這個 repo。
4. 設定：

```text
Language: Python
Build Command: 留空，或填 python -m py_compile stock_fee_bot/fees.py stock_fee_bot/line_app.py run_line_bot.py
Start Command: python run_line_bot.py
```

5. Environment Variables 加兩個值：

```text
LINE_CHANNEL_SECRET=你在 LINE Developers 複製的 Channel secret
LINE_CHANNEL_ACCESS_TOKEN=你在 LINE Developers 複製的 Channel access token
```

6. 按 Create Web Service。
7. Render 部署完成後，會給你一個網址，長得像：

```text
https://line-stock-fee-bot.onrender.com
```

## 第六段：回 LINE Developers 填 Webhook URL

1. 回 LINE Developers Console。
2. 進入 Messaging API channel。
3. 切到 Messaging API 分頁。
4. 找 Webhook URL，按 Edit。
5. 填入 Render 網址加 `/callback`，例如：

```text
https://line-stock-fee-bot.onrender.com/callback
```

6. 按 Verify。
7. 如果成功，打開 `Use webhook`。

## 第七段：關掉 LINE 官方帳號自動回覆

第一次做建議關掉官方帳號內建自動回覆，避免它跟我們的機器人同時回話。

在 LINE Official Account Manager 裡，把 Auto-reply messages 關掉。Greeting message 可以保留，也可以關掉。

## 第八段：測試

1. 在 LINE Developers 的 Messaging API 分頁找到 QR code。
2. 用你的 LINE 掃 QR code，把官方帳號加好友。
3. 傳：

```text
50 1000 6折
```

應該會回：

```text
成交金額：50,000 元
原始手續費：71 元
6折後手續費：43 元
```

## 卡住時先看三件事

1. Render 網址打開 `/health` 有沒有顯示 `{"ok": true}`。
2. LINE Developers 的 Webhook URL 是不是 `https://你的Render網址/callback`。
3. Render 的 Environment Variables 是否有填 `LINE_CHANNEL_SECRET` 和 `LINE_CHANNEL_ACCESS_TOKEN`。

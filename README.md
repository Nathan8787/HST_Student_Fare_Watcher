# 高鐵學生優惠票監控器 (THSR Student Fare Watcher)

[![zh-TW](https://img.shields.io/badge/language-繁體中文-blue.svg)](README.md)

這是一個專為台灣高鐵（THSR）設計的自動化工具，旨在協助使用者監控並尋找指定的學生優惠票。本專案由兩個核心腳本組成：

1. `thsrc_search_v2_plus.py`: 一個強大的命令列工具，用於自動搜尋高鐵班次，並將結果儲存為 CSV 檔案。它能自動處理驗證碼，並提供多種自訂選項。
2. `thsrc_watch.py`: 一個監控腳本，它會定期執行搜尋腳本，並在發現符合特定折扣關鍵字（例如「學生5折」）的車票時，透過 Gmail 寄送電子郵件通知給使用者。

## ✨ 功能特色

* **🤖 自動化搜尋**: 完全模擬使用者操作，自動化填寫查詢條件、處理驗證碼並擷取結果。
* **🎯 智慧監控**: 可設定關鍵字（如 `學生5折`、`學生88折`），持續監控直到目標票種出現。
* **📧 即時郵件通知**: 一旦發現目標票種，立即透過 Gmail 發送通知，讓您不錯過任何搶票時機。
* **⚙️ 高度可配置**: 支援自訂搜尋條件（起訖站、日期、時間）、瀏覽器引擎（Edge/Chromium）、代理伺服器等。
* **🛡️ 穩定可靠**: 內建重試機制、遮罩處理與錯誤偵測，能應對高鐵網站的動態變化，長時間穩定運行。
* **🕒 彈性排程**: 可設定監控腳本的執行頻率與自動停止時間。
* **📄 結果匯出**: 所有搜尋結果都會被整齊地儲存到 `out.csv` 檔案中，方便後續分析。

## 🛠️ 系統需求

* Python 3.7+
* 已安裝 Microsoft Edge 或 Google Chrome/Chromium 瀏覽器。

## 🚀 安裝與設定

1. **複製專案**
   如果您是透過 git clone 下載，可以跳過此步。如果不是，請確保您已將專案檔案放置在同一個資料夾中。

2. **安裝必要的 Python 套件**
   本專案依賴 `playwright` 進行瀏覽器自動化，以及 `ddddocr` 用於驗證碼辨識。

   ```bash
   pip install playwright ddddocr
   ```

3. **安裝 Playwright 瀏覽器驅動**
   此指令會下載並安裝 Chromium 核心，這是 Playwright 運行所必需的。

   ```bash
   python -m playwright install chromium
   ```

4. **設定 Gmail 應用程式密碼**
   `thsrc_watch.py` 使用 Gmail 的 SMTP 服務來寄送郵件。基於安全性，Google 要求使用「應用程式密碼」而非您的主要登入密碼。

   * 前往您的 [Google 帳戶安全性設定](https://myaccount.google.com/security)。
   * 確認您已啟用「兩步驟驗證」。
   * 在「應用程式密碼」區塊，建立一組新的 16 位密碼，並將其妥善保存。這將是您在執行監控腳本時需要用到的密碼。

## 📖 使用教學

本專案分為「單次搜尋」與「持續監控」兩種模式。

### 1. 單次搜尋 (`thsrc_search_v2_plus.py`)

此腳本用於執行一次性的車票查詢，並將結果存入 CSV 檔案。

**指令格式：**

```bash
python thsrc_search_v2_plus.py --origin <出發站> --dest <到達站> --date <日期> --time <時間> [--student <學生票數>] [--adult <成人票數>] [--csv <輸出路徑>]
```

**參數說明：**
* `--origin`: 出發站 (例如: `台北`, `台中`)
* `--dest`: 到達站 (例如: `左營`, `台南`)
* `--date`: 乘車日期 (格式: `YYYY-MM-DD`)
* `--time`: 預計出發時間 (格式: `HH:MM`，例如 `15:00`)
* `--student`: 學生票張數 (預設: `0`)
* `--adult`: 成人票張數 (預設: `1`)
* `--csv`: 輸出 CSV 檔案的路徑 (預設: `thsrc_results.csv`)
* `--engine`: 瀏覽器引擎 (`edge` 或 `chromium`，預設: `edge`)
* `--headless`: 在背景執行，不開啟瀏覽器視窗。

**使用範例：**
搜尋 2025年10月20日 15:00 後，從「台北」到「台中」的 1 張學生票。

```bash
python thsrc_search_v2_plus.py --origin 台北 --dest 台中 --date 2025-10-20 --time 15:00 --student 1 --adult 0 --csv out.csv
```

### 2. 持續監控並郵件通知 (`thsrc_watch.py`)

此腳本會定期（預設 3-5 分鐘）執行 `thsrc_search_v2_plus.py`，檢查結果中是否包含指定的優惠票，若有則寄送 Gmail 通知。

**指令格式：**

```bash
python thsrc_watch.py --scraper "<完整的搜尋指令>" --sender <寄件Gmail> --app_password <Gmail應用程式密碼> --to <收件Email> [--until <停止時間>]
```

**參數說明：**
* `--scraper`: **(核心參數)** 一個包含完整 `thsrc_search_v2_plus.py` 指令的字串。請務必用雙引號 `""` 包覆。
* `--sender`: 您的 Gmail 帳號。
* `--app_password`: 您先前產生的 16 位 Gmail 應用程式密碼。
* `--to`: 接收通知的 Email 地址（可以是任何信箱）。
* `--csv`: 指定搜尋腳本輸出的 CSV 路徑 (預設: `out.csv`)。
* `--min_sec`, `--max_sec`: 每輪監控的最小/最大隨機等待秒數 (預設: 180-300 秒)。
* `--until`: 自動停止監控的時間 (格式: `YYYY-MM-DD HH:MM`)。

**使用範例：**
持續監控從「台北」到「台中」的學生票，直到 2025年10月15日 16:10 為止。一有符合 `學生88折` 的票，就從 `your.email@gmail.com` 寄信到 `recipient@example.com`。

```bash
python thsrc_watch.py --scraper "python thsrc_search_v2_plus.py --origin 台北 --dest 台中 --date 2025-10-20 --time 15:00 --student 1 --csv out.csv" --sender your.email@gmail.com --app_password your_16_digit_app_password --to recipient@example.com --until "2025-10-15 16:10"
```
> **注意**: 在 `thsrc_watch.py` 的 `KEYWORD` 變數中，您可以自行修改想要尋找的折扣文字，預設為 `學生88折`。

## 📁 檔案結構

```
HST_Student_Fare_Watcher/
│
├── thsrc_search_v2_plus.py   # 核心搜尋腳本
├── thsrc_watch.py            # 自動監控與通知腳本
├── out.csv                   # 預設的搜尋結果輸出檔案
├── .state/                   # 狀態目錄 (會自動建立)
│   └── notified.txt          # 記錄已通知的車次，避免重複寄信
└── README.md                 # 本說明文件
```

## ⚠️ 注意事項

* 本工具僅供個人學習和研究目的使用，請勿用於商業用途或進行任何可能影響高鐵訂票系統公平性的行為。
* 高鐵網站的前端結構可能隨時變更，若腳本失效，可能需要根據網站的更新進行調整。
* 請遵守高鐵公司的相關規定，並以負責任的態度使用本工具。
* 執行監控腳本時，您的 Gmail 帳號與應用程式密碼會以明文形式出現在命令列歷史紀錄中，請注意操作環境的安全性。

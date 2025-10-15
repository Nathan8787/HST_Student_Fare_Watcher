# -*- coding: utf-8 -*-
# thsrc_search_v2_plus.py
# 需求:
#   pip install playwright ddddocr
#   python -m playwright install chromium
#   （如要走 Edge）請在本機已安裝 Microsoft Edge
#
# 執行例:
#   python thsrc_search_v2_plus.py --origin 台北 --dest 台中 --date 2025-10-20 --time 15:00 --adult 0 --student 1 --csv out.csv --engine edge
#
# 重要說明：
# - 以你 v2 的做法為主：Submit 使用 no_wait_after=True、顯式等遮罩消失、等待 Step2 結果區塊或錯誤。
# - 這版加強點：更穩定的遮罩偵測與「強制解除」、更完整的錯誤訊息檢查、可選 Edge/Chromium、可自定 UA 與 Proxy。
# - 擷取欄位：出發時間、抵達時間、車程、車次、日期、是否學生折扣、折數（若有文字如「學生88折」）、是否為目前頁面預設選取列車。

import argparse
import csv
import os
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import ddddocr
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

URL = "https://irs.thsrc.com.tw/IMINT/?utm_source=thsrc&utm_medium=btnlink&utm_term=booking"

# -----------------------------
# 小工具
# -----------------------------
def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")

def human_sleep(a=0.15, b=0.45):
    time.sleep(random.uniform(a, b))

def ensure_dir(p: str):
    Path(p).parent.mkdir(parents=True, exist_ok=True)

# -----------------------------
# 遮罩處理與頁面等待
# -----------------------------
def wait_mask_then_clear_if_stuck(page, check_every_ms=400, hard_timeout_ms=16000):
    """
    等待 loading 遮罩消失；若超時則呼叫頁面現成的 hideMaskFrame() 嘗試解除。
    """
    start = time.time()
    while True:
        try:
            ok = page.evaluate(
                """() => {
                    const isHidden = (el) => !el || el.style.display === 'none' || getComputedStyle(el).display === 'none';
                    const a = document.querySelector('#divMaskFrame');
                    const b = document.querySelector('#loadingMask');
                    const c = document.querySelector('#BusyBoxDiv');
                    return isHidden(a) && isHidden(b) && isHidden(c);
                }"""
            )
            if ok:
                return True
        except Exception:
            pass

        if (time.time() - start) * 1000 > hard_timeout_ms:
            log("遮罩疑似卡住，嘗試呼叫 hideMaskFrame() 強制解除")
            try:
                page.evaluate("hideMaskFrame && hideMaskFrame();")
            except Exception:
                pass
            # 再給它一點時間
            time.sleep(0.6)
            try:
                ok = page.evaluate(
                    """() => {
                        const isHidden = (el) => !el || el.style.display === 'none' || getComputedStyle(el).display === 'none';
                        const a = document.querySelector('#divMaskFrame');
                        const b = document.querySelector('#loadingMask');
                        const c = document.querySelector('#BusyBoxDiv');
                        return isHidden(a) && isHidden(b) && isHidden(c);
                    }"""
                )
                return ok
            except Exception:
                return False

        time.sleep(check_every_ms / 1000.0)

def wait_step2_or_error(page, timeout_ms=15000):
    """
    等待「選擇車次」(Step2) 結果區塊，或錯誤區塊顯示。
    回傳 'step2' / 'error' / 'none'
    """
    start = time.time()
    while (time.time() - start) * 1000 <= timeout_ms:
        try:
            exist_step2 = page.locator("#BookingS2Form_TrainQueryDataViewPanel").first.is_visible(timeout=500)
            if exist_step2:
                return "step2"
        except Exception:
            pass

        try:
            # divErrMSG 只有在內部有字或 li 時會顯示，保守地只要顯示就算 error
            err_block = page.locator("#divErrMSG")
            if err_block.count() > 0 and err_block.first.is_visible(timeout=200):
                return "error"
        except Exception:
            pass

        time.sleep(0.25)

    return "none"

def read_error_text(page):
    try:
        if page.locator("#divErrMSG").first.is_visible(timeout=500):
            txt = page.locator("#divErrMSG").inner_text(timeout=500)
            return re.sub(r"\s+", " ", txt).strip()
    except Exception:
        pass
    return ""

# -----------------------------
# 初始頁面操作
# -----------------------------
def close_consent(page):
    for label in ["我同意", "同意", "我同意，繼續", "同意並繼續"]:
        try:
            page.get_by_role("button", name=label, exact=False).click(timeout=1200)
            human_sleep()
            return
        except Exception:
            pass
    try:
        page.get_by_text("同意", exact=False).first.click(timeout=1200)
        human_sleep()
    except Exception:
        pass

def select_station(page, which: str, name: str):
    sel = page.locator('select[name="selectStartStation"]') if which == "出發" \
          else page.locator('select[name="selectDestinationStation"]')
    sel.select_option(label=name)
    human_sleep()

def set_date(page, date_str: str):
    # flatpickr: 真正送出的值在隱藏 input #toTimeInputField，格式需 YYYY/MM/DD
    yyyy, mm, dd = date_str.split("-")
    v = f"{yyyy}/{int(mm):02d}/{int(dd):02d}"
    page.evaluate(
        """(val)=>{
            const el = document.querySelector('#toTimeInputField');
            if(!el) return;
            el.value = val;
            el.setAttribute('value', val);
            el.dispatchEvent(new Event('input', {bubbles:true}));
            el.dispatchEvent(new Event('change', {bubbles:true}));
            if (window.BookingS1 && BookingS1.typesoftrainCheck) {
                try { BookingS1.typesoftrainCheck(); } catch(e){}
            }
        }""",
        v
    )
    human_sleep()

def set_time(page, time_label: str):
    page.locator('select[name="toTimeTable"]').select_option(label=time_label)
    human_sleep()

def set_student_count(page, n: int):
    page.locator('select[name="ticketPanel:rows:4:ticketAmount"]').select_option(value=f"{n}P")
    human_sleep()

def set_adult_count(page, n: int):
    page.locator('select[name="ticketPanel:rows:0:ticketAmount"]').select_option(value=f"{n}F")
    human_sleep()

# -----------------------------
# 驗證碼
# -----------------------------
class CaptchaSolver:
    def __init__(self):
        self.ocr = ddddocr.DdddOcr()

    def solve_once(self, page) -> str:
        # 先刷新一次降低殘影
        try:
            page.locator("#BookingS1Form_homeCaptcha_reCodeLink").click(timeout=800)
            page.wait_for_timeout(450)
        except Exception:
            pass

        img = page.locator("#BookingS1Form_homeCaptcha_passCode")
        img.wait_for(timeout=6000)
        path = "captcha.png"
        img.screenshot(path=path)
        with open(path, "rb") as f:
            raw = f.read()
        try:
            os.remove(path)
        except Exception:
            pass
        res = self.ocr.classification(raw)
        # 清理成英數（網站常見 4 位）
        res = re.sub(r"[^0-9a-zA-Z]", "", res or "")
        return res

    def fill(self, page, text: str):
        sc = page.locator("#securityCode")
        sc.fill(text)
        # 觸發事件
        page.evaluate(
            """() => {
                const el = document.querySelector('#securityCode');
                if (!el) return;
                el.dispatchEvent(new Event('input', {bubbles:true}));
                el.dispatchEvent(new Event('change', {bubbles:true}));
                el.blur();
            }"""
        )

def handle_captcha(page, max_try=6) -> bool:
    solver = CaptchaSolver()
    for i in range(max_try):
        try:
            ans = solver.solve_once(page)
            log(f"OCR 辨識結果: {ans}")
            if not ans:
                continue
            solver.fill(page, ans)
            return True
        except Exception as e:
            log(f"處理驗證碼失敗（{i+1}/{max_try}）：{e}")
    log("超過最大重試次數，無法處理驗證碼")
    return False

# -----------------------------
# 送出查詢與重試邏輯
# -----------------------------
def click_search(page):
    # AJAX 提交，避免卡在「等待導航」
    page.locator("#SubmitButton").click(no_wait_after=True)

def submit_and_wait_step2(page, max_submit_retries=5):
    """
    - 送出查詢
    - 等遮罩 → 等 Step2 或錯誤
    - 若錯誤含驗證碼/錯誤字樣，重新解一次驗證碼後再送
    """
    for attempt in range(max_submit_retries):
        click_search(page)
        wait_mask_then_clear_if_stuck(page, hard_timeout_ms=18000)
        state = wait_step2_or_error(page, timeout_ms=18000)

        if state == "step2":
            return True
        elif state == "error":
            err = read_error_text(page)
            log(f"提交後出現錯誤：{err or '(無內容)'}")
            if "驗證碼" in err or "錯誤" in err or "請重新輸入" in err:
                log(f"嘗試重新解驗證碼並重送（{attempt+1} / {max_submit_retries}）")
                if not handle_captcha(page):
                    return False
                continue
            else:
                # 不是驗證碼錯誤，多半是其他條件未通過，直接返回
                return False
        else:
            # 兩者都沒等到，當作超時，嘗試再解一次驗證碼並重送
            log(f"等待結果超時（{attempt+1} / {max_submit_retries}），嘗試再送")
            try:
                handle_captcha(page)  # 有些情況是驗證碼過期
            except Exception:
                pass
            continue
    return False

# -----------------------------
# 解析 Step2 車次清單
# -----------------------------
def scrape_trains_on_step2(page):
    """
    回傳 list[dict]：
        departure, arrival, estimated, code, date, student_discount(bool), discount_text, selected(bool)
    """
    root = page.locator("#BookingS2Form_TrainQueryDataViewPanel")
    rows = root.locator(".result-listing label.result-item")
    n = rows.count()
    data = []

    for i in range(n):
        row = rows.nth(i)
        radio = row.locator("input.uk-radio")
        departure = radio.get_attribute("querydeparture") or ""
        arrival = radio.get_attribute("queryarrival") or ""
        estimated = radio.get_attribute("queryestimatedtime") or ""
        code = radio.get_attribute("querycode") or ""
        date = radio.get_attribute("querydeparturedate") or ""

        # 折扣
        discount_text = ""
        try:
            discount_text = row.locator(".discount span").all_inner_texts()
            discount_text = " ".join([t.strip() for t in discount_text if t.strip()])
        except Exception:
            pass

        student_discount = "學生" in discount_text or "學⽣" in discount_text  # 容錯

        # 是否為目前預選
        selected = False
        try:
            selected = (radio.is_checked() or "active" in (row.get_attribute("class") or ""))
        except Exception:
            pass

        data.append({
            "date": date,
            "code": code,
            "departure": departure,
            "arrival": arrival,
            "estimated": estimated,
            "student_discount": student_discount,
            "discount_text": discount_text,
            "selected": selected,
        })
    return data

# -----------------------------
# CSV
# -----------------------------
def save_csv(rows, csv_path):
    if not rows:
        log("沒有可寫入的資料")
        return
    ensure_dir(csv_path)
    fieldnames = ["date", "code", "departure", "arrival", "estimated", "student_discount", "discount_text", "selected"]
    write_header = not os.path.exists(csv_path)
    with open(csv_path, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            w.writeheader()
        for r in rows:
            w.writerow(r)
    log(f"已寫入 {len(rows)} 筆到 {csv_path}")

# -----------------------------
# 主流程
# -----------------------------
def main():
    ap = argparse.ArgumentParser(description="THSR 查詢（Playwright + ddddocr）")
    ap.add_argument("--origin", required=True, help="出發站，例如 台北 / 南港 / 板橋 / 桃園 / 新竹 / 台中 / 嘉義 / 台南 / 左營")
    ap.add_argument("--dest", required=True, help="到達站")
    ap.add_argument("--date", required=True, help="乘車日期 YYYY-MM-DD")
    ap.add_argument("--time", required=True, help="出發時間下拉文字，例如 15:00")
    ap.add_argument("--adult", type=int, default=1, help="全票張數")
    ap.add_argument("--student", type=int, default=0, help="學生票張數")
    ap.add_argument("--csv", default="thsrc_results.csv", help="輸出 CSV 路徑")
    ap.add_argument("--engine", choices=["edge", "chromium"], default="edge", help="瀏覽器引擎（預設 edge）")
    ap.add_argument("--headless", action="store_true", help="啟用 headless 模式")
    ap.add_argument("--proxy", default="", help="Proxy，如 http://HOST:PORT")
    ap.add_argument("--ua", default="", help="自訂 User-Agent（空字串則使用預設 Edge UA）")
    args = ap.parse_args()

    # 預設用 Edge 的 UA（比 Chromium 更像真人流量）
    default_edge_ua = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0"
    )
    user_agent = args.ua or default_edge_ua

    with sync_playwright() as p:
        launch_kwargs = dict(headless=args.headless)
        if args.engine == "edge":
            # 使用 Edge channel（需本機有 Edge）
            launch_kwargs["channel"] = "msedge"
        # proxy 在 browser.launch 層級（若有）
        if args.proxy:
            launch_kwargs["proxy"] = {"server": args.proxy}

        browser = p.chromium.launch(**launch_kwargs)

        context = browser.new_context(
            locale="zh-TW",
            timezone_id="Asia/Taipei",
            viewport={"width": 1280, "height": 900},
            user_agent=user_agent,
        )

        # 反自動化痕跡（常見檢查項）
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'languages', { get: () => ['zh-TW','zh','en-US','en'] });
            window.chrome = { runtime: {} };
            const originalQuery = window.navigator.permissions && window.navigator.permissions.query;
            if (originalQuery) {
              window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                  Promise.resolve({ state: Notification.permission }) :
                  originalQuery(parameters)
              );
            }
        """)

        page = context.new_page()
        page.set_default_timeout(20000)

        try:
            log("前往首頁")
            page.goto(URL, wait_until="domcontentloaded", timeout=60000)
            human_sleep()

            close_consent(page)

            select_station(page, "出發", args.origin)
            select_station(page, "到達", args.dest)
            set_date(page, args.date)
            set_time(page, args.time)
            set_adult_count(page, args.adult)
            set_student_count(page, args.student)

            # 處理驗證碼
            log("嘗試解驗證碼")
            if not handle_captcha(page):
                raise RuntimeError("無法處理驗證碼")

            # 送出並等待 Step2
            log("送出查詢")
            ok = submit_and_wait_step2(page, max_submit_retries=6)
            if not ok:
                # 儲存除錯資料
                Path("debug").mkdir(exist_ok=True)
                page.screenshot(path="debug/failed.png", full_page=True)
                with open("debug/failed.html", "w", encoding="utf-8") as f:
                    f.write(page.content())
                raise RuntimeError("送出查詢失敗或超時")

            log("已進入 Step2，開始擷取車次列表")
            rows = scrape_trains_on_step2(page)
            if not rows:
                log("Step2 無資料，儲存除錯快照")
                Path("debug").mkdir(exist_ok=True)
                page.screenshot(path="debug/no_rows.png", full_page=True)
                with open("debug/no_rows.html", "w", encoding="utf-8") as f:
                    f.write(page.content())
            else:
                save_csv(rows, args.csv)

            log("完成")
            time.sleep(1.2)  # 保留觀察
        except Exception as e:
            log(f"發生例外：{e}")
            # 例外時也輸出一次快照
            try:
                Path("debug").mkdir(exist_ok=True)
                page.screenshot(path="debug/exception.png", full_page=True)
                with open("debug/exception.html", "w", encoding="utf-8") as f:
                    f.write(page.content())
            except Exception:
                pass
            sys.exit(1)
        finally:
            context.close()
            browser.close()

if __name__ == "__main__":
    main()

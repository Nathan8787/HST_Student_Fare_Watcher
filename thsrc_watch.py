# -*- coding: utf-8 -*-
# 監看 out.csv 的 discount_text 是否含「學生5折」，若有就寄 Gmail。
# 會每隔 3~5 分鐘重跑你的抓票腳本一次（帶隨機抖動），直到手動停止或到達指定時間。
#
# 需求：內建 smtplib / email 即可，無需額外套件。
#
# 範例：
# python thsrc_watch.py --scraper "python thsrc_search_v2_plus.py --origin 台北 --dest 台中 --date 2025-10-20 --time 15:00 --adult 0 --student 1 --csv out.csv --engine edge"  --csv out.csv   --sender gogle130355710@gmail.com  --app_password xyqrcfauievkzqap  --to gogle130355710@gmail.com --until "2025-10-15 16:10"

import argparse
import csv
import os
import random
import smtplib
import subprocess
import sys
import time
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

KEYWORD = "學生88折"

def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def load_notified(state_path: str):
    if not os.path.exists(state_path):
        return set()
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            lines = [ln.strip() for ln in f if ln.strip()]
        return set(lines)
    except:
        return set()

def save_notified(state_path: str, keys_set: set):
    Path(state_path).parent.mkdir(parents=True, exist_ok=True)
    with open(state_path, "w", encoding="utf-8") as f:
        for k in sorted(keys_set):
            f.write(k + "\n")

def run_scraper(cmd: str) -> int:
    log(f"執行抓票：{cmd}")
    try:
        # shell=True 讓你可整段丟字串；若不喜歡可改成陣列形式
        return subprocess.call(cmd, shell=True)
    except Exception as e:
        log(f"抓票腳本執行失敗：{e}")
        return 1

def read_hits(csv_path: str, keyword: str):
    """回傳本次偵測命中的列（list of dict）"""
    rows = []
    if not os.path.exists(csv_path):
        log(f"找不到 CSV：{csv_path}")
        return rows
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        for row in r:
            text = (row.get("discount_text") or "").strip()
            if keyword in text:
                rows.append(row)
    return rows

def make_key(row: dict) -> str:
    # 用幾個欄位組成唯一 key，避免重複寄
    return "|".join([
        row.get("date","").strip(),
        row.get("code","").strip(),
        row.get("departure","").strip(),
        row.get("arrival","").strip(),
        row.get("discount_text","").strip(),
    ])

def send_gmail_smtp(sender: str, app_password: str, to: str, subject: str, html_body: str, text_body: str = None):
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject

    # 純文字 & HTML 兩種都放，增加相容性
    text_body = text_body or "See HTML content."
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(sender, app_password)
        smtp.send_message(msg)

def format_email(rows):
    # 產生 email 內容
    lines_txt = []
    lines_html = []
    for r in rows:
        line = f"{r.get('date')}  車次 {r.get('code')}  {r.get('departure')} → {r.get('arrival')}  車程 {r.get('estimated')}  折扣:{r.get('discount_text')}"
        lines_txt.append(line)
        lines_html.append(f"<li>{line}</li>")
    text_body = "偵測到學生5折的車次：\n" + "\n".join(lines_txt)
    html_body = f"""
    <html><body>
    <p>偵測到 <b>學生5折</b> 的車次：</p>
    <ul>{''.join(lines_html)}</ul>
    <p>時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </body></html>
    """
    return text_body, html_body

def parse_until(until_str: str):
    if not until_str:
        return None
    # 允許 "YYYY-MM-DD HH:MM" 或 "YYYY-MM-DD HH:MM:SS"
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(until_str, fmt)
        except:
            pass
    raise ValueError("until 格式應為 'YYYY-MM-DD HH:MM' 或 'YYYY-MM-DD HH:MM:SS'")

def main():
    ap = argparse.ArgumentParser(description="THSR 學生5折監看器（每 3~5 分鐘輪詢）")
    ap.add_argument("--scraper", required=True, help="執行抓票指令（字串）")
    ap.add_argument("--csv", default="out.csv", help="抓票輸出的 CSV 路徑")
    ap.add_argument("--sender", required=True, help="寄件者 Gmail（需已啟用兩步驟＋App Password）")
    ap.add_argument("--app_password", required=True, help="Gmail 應用程式專用密碼（16 碼）")
    ap.add_argument("--to", required=True, help="收件者 Email")
    ap.add_argument("--state", default=".state/notified.txt", help="已通知記錄檔，避免重複寄")
    ap.add_argument("--min_sec", type=int, default=180, help="每輪最少等待秒數（預設 180=3 分鐘）")
    ap.add_argument("--max_sec", type=int, default=300, help="每輪最多等待秒數（預設 300=5 分鐘）")
    ap.add_argument("--until", default="", help="到此時間自動停止（例：2025-10-20 23:59）")
    args = ap.parse_args()

    until_dt = parse_until(args.until) if args.until else None
    notified = load_notified(args.state)

    log("開始監看（Ctrl+C 可中止）")
    try:
        while True:
            if until_dt and datetime.now() >= until_dt:
                log("到達指定時間，停止。")
                break

            rc = run_scraper(args.scraper)
            if rc != 0:
                log(f"抓票腳本回傳非 0（{rc}），略過本輪分析。")

            rows = read_hits(args.csv, KEYWORD)
            # 去除已寄過的
            new_rows = []
            new_keys = []
            for r in rows:
                k = make_key(r)
                if k not in notified:
                    new_rows.append(r)
                    new_keys.append(k)

            if new_rows:
                text_body, html_body = format_email(new_rows)
                try:
                    send_gmail_smtp(
                        sender=args.sender,
                        app_password=args.app_password,
                        to=args.to,
                        subject=f"[THSR] 偵測到 {KEYWORD} 共 {len(new_rows)} 筆",
                        html_body=html_body,
                        text_body=text_body,
                    )
                    log(f"已寄出通知信（{len(new_rows)} 筆）")
                    # 記錄避免重複寄
                    notified.update(new_keys)
                    save_notified(args.state, notified)
                except Exception as e:
                    log(f"寄信失敗：{e}")

            # 等待下一輪（3~5 分鐘隨機）
            wait_s = random.randint(args.min_sec, args.max_sec)
            log(f"下一輪等待 {wait_s} 秒…")
            time.sleep(wait_s)

    except KeyboardInterrupt:
        log("手動停止。")

if __name__ == "__main__":
    main()

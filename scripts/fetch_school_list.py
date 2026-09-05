#!/usr/bin/env python3
"""
fetch_school_list.py - NEIS 학교기본정보(schoolInfo) 전량 수집
키 없이도 호출 가능(NEIS Open API는 인증키 없이 기본 트래픽 허용).

출력: _rawdata/school_list_raw.json
"""
import json, os, sys, time
import requests

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "_rawdata", "school_list_raw.json")

BASE = "https://open.neis.go.kr/hub/schoolInfo"
PAGE_SIZE = 1000
API_KEY = os.environ.get("NEIS_API_KEY") or "3d2634b6a79249e4b7a773a27b705cec"


def fetch_page(page_no, attempt=1):
    params = {"KEY": API_KEY, "Type": "json", "pIndex": page_no, "pSize": PAGE_SIZE}
    try:
        r = requests.get(BASE, params=params, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        return r.json()
    except Exception as e:
        if attempt >= 5:
            raise
        print(f"  [재시도 {attempt}] page {page_no}: {e}")
        time.sleep(3)
        return fetch_page(page_no, attempt + 1)


def main():
    all_rows = []
    page = 1
    total_count = None
    while True:
        data = fetch_page(page)
        body = data.get("schoolInfo")
        if not body:
            print("응답 이상:", json.dumps(data, ensure_ascii=False)[:300])
            break
        head = body[0]["head"]
        if total_count is None:
            total_count = head[0]["list_total_count"]
            print(f"전체 학교 수: {total_count}")
        rows = body[1]["row"] if len(body) > 1 else []
        if not rows:
            break
        all_rows.extend(rows)
        print(f"  page {page}: 누적 {len(all_rows)} / {total_count}")
        if len(all_rows) >= total_count:
            break
        page += 1
        if page > 30:
            print("안전장치: 30페이지 초과, 중단")
            break
        time.sleep(0.2)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(all_rows, f, ensure_ascii=False)
    print(f"\n총 {len(all_rows)}건 저장 -> {OUT}")


if __name__ == "__main__":
    main()

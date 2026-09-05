#!/usr/bin/env python3
"""
fetch_school_meal.py - NEIS 급식식단정보(mealServiceDietInfo)를 학교별로 전량 수집한다.
학교당 1~수 콜(pSize=1000, 날짜 필터 없이 전체 이력)로 가져올 수 있어, 단지 기본정보처럼
1건씩 조회해야 하는 구조보다 훨씬 빠르다.

이미 _rawdata/meal_detail.json에 있는 학교는 건너뛰고, --limit개만 처리한다.
매일/여러 번 나눠 실행하면 전체가 채워진다.

사용법: python scripts/fetch_school_meal.py [--limit N]
"""
import json, os, sys, time, argparse
from datetime import date, timedelta
import requests

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_LIST = os.path.join(ROOT, "_rawdata", "school_list_raw.json")
DETAIL_CACHE = os.path.join(ROOT, "_rawdata", "meal_detail.json")

API_KEY = os.environ.get("NEIS_API_KEY") or "3d2634b6a79249e4b7a773a27b705cec"
BASE = "https://open.neis.go.kr/hub/mealServiceDietInfo"
PAGE_SIZE = 1000

DEFAULT_LIMIT = 12700  # 기본은 전체 한 번에 시도 (필요시 --limit으로 조절)

# 전체 이력(수년치)을 다 저장하면 원산지정보 등으로 용량이 기하급수로 커져서(테스트 결과 학교당
# 수백KB~1MB) 최근 구간만 유지한다. 매 실행마다 이 구간으로 "교체"되므로 항상 최신 상태 유지.
FROM_YMD = (date.today() - timedelta(days=60)).strftime("%Y%m%d")
TO_YMD = (date.today() + timedelta(days=75)).strftime("%Y%m%d")


def fetch_school_meals(atpt_code, schul_code):
    """한 학교의 최근 구간(FROM_YMD~TO_YMD) 급식 이력을 페이지네이션으로 모두 가져온다."""
    rows = []
    page = 1
    while True:
        params = {
            "KEY": API_KEY, "Type": "json", "pIndex": page, "pSize": PAGE_SIZE,
            "ATPT_OFCDC_SC_CODE": atpt_code, "SD_SCHUL_CODE": schul_code,
            "MLSV_FROM_YMD": FROM_YMD, "MLSV_TO_YMD": TO_YMD,
        }
        try:
            r = requests.get(BASE, params=params, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            return rows if rows else None

        body = data.get("mealServiceDietInfo")
        if not body:
            # RESULT 코드가 데이터없음(INFO-200)인 정상 케이스 포함
            break
        page_rows = body[1]["row"] if len(body) > 1 else []
        if not page_rows:
            break
        rows.extend(page_rows)
        total = body[0]["head"][0]["list_total_count"]
        if len(rows) >= total:
            break
        page += 1
        if page > 20:
            break
    return rows


def compact(rows):
    """저장 용량을 줄이기 위해 필요한 필드만 추출 (원산지정보는 용량 대비 검색가치가
    낮아 제외 - 테스트 결과 전체 용량의 61%를 차지했음)."""
    out = []
    for r in rows:
        out.append({
            "d": r.get("MLSV_YMD"),
            "t": r.get("MMEAL_SC_NM"),
            "m": r.get("DDISH_NM"),
            "cal": r.get("CAL_INFO"),
            "ntr": r.get("NTR_INFO"),
        })
    return sorted(out, key=lambda x: x["d"] or "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    args = ap.parse_args()

    schools = json.loads(open(RAW_LIST, encoding="utf-8").read())
    detail_map = {}
    if os.path.exists(DETAIL_CACHE):
        detail_map = json.loads(open(DETAIL_CACHE, encoding="utf-8").read())

    remaining = [s for s in schools if s.get("SD_SCHUL_CODE") and s["SD_SCHUL_CODE"] not in detail_map]
    print(f"전체 {len(schools)}개 / 확보 {len(detail_map)}개 / 남음 {len(remaining)}개")

    if not remaining:
        print("모든 학교 급식 데이터 수집 완료!")
        return

    todo = remaining[: args.limit]
    print(f"이번 실행에서 {len(todo)}개 학교 처리 시도...")

    ok, empty, fail = 0, 0, 0
    for i, s in enumerate(todo, 1):
        code = s["SD_SCHUL_CODE"]
        rows = fetch_school_meals(s["ATPT_OFCDC_SC_CODE"], code)
        if rows is None:
            fail += 1
        elif len(rows) == 0:
            detail_map[code] = []
            empty += 1
        else:
            detail_map[code] = compact(rows)
            ok += 1

        if i % 100 == 0:
            print(f"  진행 {i}/{len(todo)} (성공 {ok}, 데이터없음 {empty}, 실패 {fail})")
            with open(DETAIL_CACHE, "w", encoding="utf-8") as f:
                json.dump(detail_map, f, ensure_ascii=False)
        time.sleep(0.03)

    with open(DETAIL_CACHE, "w", encoding="utf-8") as f:
        json.dump(detail_map, f, ensure_ascii=False)

    total_filled = len(detail_map)
    print(f"\n완료: 성공 {ok} / 데이터없음 {empty} / 실패 {fail}")
    print(f"누적 확보: {total_filled} / {len(schools)} ({total_filled*100//len(schools)}%)")


if __name__ == "__main__":
    main()

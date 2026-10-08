#!/usr/bin/env python3
"""
fetch_school_schedule.py - NEIS 학사일정(SchoolSchedule)을 학교별로 수집해 요약·압축 저장한다.

- 학년도(3월~다음해 2월) 1회 호출/학교(pSize=1000)
- 공휴일·토요휴업일 행은 버리고, 같은 행사명의 연속 일자는 하나의 구간으로 합친다
- 방학·개학·시험·재량휴업일 등 검색 수요가 큰 항목은 정규식으로 요약(summary)한다
출력: _rawdata/schedule.json  {학교코드: {"ay":2026,"s":{요약},"ev":[[시작,종료,행사명],...]}}

사용법: python scripts/fetch_school_schedule.py [--limit N] [--workers 6]
"""
import json, os, re, sys, time, argparse
from datetime import date, datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_LIST = os.path.join(ROOT, "_rawdata", "school_list_raw.json")
OUT = os.path.join(ROOT, "_rawdata", "schedule.json")

API_KEY = os.environ.get("NEIS_API_KEY") or "3d2634b6a79249e4b7a773a27b705cec"
BASE = "https://open.neis.go.kr/hub/SchoolSchedule"

today = date.today()
AY = today.year if today.month >= 3 else today.year - 1
FROM_YMD, TO_YMD = f"{AY}0301", f"{AY + 1}0228"

SUMMER_RE = re.compile(r"^(여름|하계)\s*방학(\(.*\))?$")
WINTER_RE = re.compile(r"^(겨울|동계)\s*방학(\(.*\))?$|^학년말\s*방학|^학기말\s*방학|^겨울\s*방학\(?전학년\)?$")
SPRING_RE = re.compile(r"^봄\s*방학$")
OPEN_RE = re.compile(r"(개학식|시업식|입학식)")
EXAM_RE = re.compile(r"(중간고사|기말고사|정기고사|지필평가|정기시험|학기말고사|[1-4]회고사|[1-4]차\s*고사)")
GRADE_RE = re.compile(r"(학력평가|모의평가|성취도평가|학업성취도)")
DISC_RE = re.compile(r"(재량휴업|학교장\s*재량|개교기념)")


def ymd(s):
    return datetime.strptime(s, "%Y%m%d").date()


def iso(d):
    return d.strftime("%Y-%m-%d")


def fetch_rows(atpt, code):
    rows, page = [], 1
    while True:
        params = {"KEY": API_KEY, "Type": "json", "pIndex": page, "pSize": 1000,
                  "ATPT_OFCDC_SC_CODE": atpt, "SD_SCHUL_CODE": code,
                  "AA_FROM_YMD": FROM_YMD, "AA_TO_YMD": TO_YMD}
        for attempt in range(3):
            try:
                r = requests.get(BASE, params=params, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
                r.raise_for_status()
                data = r.json()
                break
            except Exception:
                data = None
                time.sleep(1.5 * (attempt + 1))
        if data is None:
            return None
        body = data.get("SchoolSchedule")
        if not body:
            return rows
        page_rows = body[1]["row"] if len(body) > 1 else []
        rows.extend(page_rows)
        if len(rows) >= body[0]["head"][0]["list_total_count"] or not page_rows or page > 5:
            return rows
        page += 1


def merge_ranges(items):
    """[(date, name)] -> [[start, end, name]] (같은 이름이 4일 이내 간격이면 한 구간)"""
    by_name = {}
    for d, n in items:
        by_name.setdefault(n, []).append(d)
    out = []
    for n, ds in by_name.items():
        ds.sort()
        start = prev = ds[0]
        for d in ds[1:]:
            if (d - prev).days > 4:
                out.append([iso(start), iso(prev), n])
                start = d
            prev = d
        out.append([iso(start), iso(prev), n])
    out.sort(key=lambda x: (x[0], x[2]))
    return out


def summarize(rows):
    kept, sat = [], 0
    summer, winter, spring = [], [], []
    exams, discs, opens = [], [], []
    for r in rows:
        n = (r.get("EVENT_NM") or "").strip()
        if not n:
            continue
        d = ymd(r["AA_YMD"])
        kind = r.get("SBTR_DD_SC_NM") or ""
        if kind == "공휴일":
            continue
        if n == "토요휴업일":
            sat += 1
            continue
        kept.append((d, n))
        compact = re.sub(r"\s+", " ", n)
        if SUMMER_RE.match(compact) and 6 <= d.month <= 9:
            summer.append(d)
        elif WINTER_RE.match(compact) and (d.month in (12, 1, 2, 3)):
            winter.append(d)
        elif SPRING_RE.match(compact):
            spring.append(d)
        if EXAM_RE.search(n) and not GRADE_RE.search(n):
            exams.append((d, n))
        if DISC_RE.search(n) and kind == "휴업일":
            discs.append(d)
        if OPEN_RE.search(n) and "방학" not in n:
            opens.append((d, n))

    s = {}
    if summer:
        s["summer"] = [iso(min(summer)), iso(max(summer))]
    if winter:
        s["winter"] = [iso(min(winter)), iso(max(winter))]
    if spring:
        s["spring"] = [iso(min(spring)), iso(max(spring))]
    first_open = [d for d, n in opens if d.month in (2, 3)]
    if first_open:
        s["open1"] = iso(min(first_open))
    open2 = [d for d, n in opens if d.month in (8, 9) or (summer and d > max(summer) and d.month in (7, 8, 9))]
    if open2:
        s["open2"] = iso(min(open2))
    elif "summer" in s:
        d = ymd(s["summer"][1].replace("-", "")) + timedelta(days=1)
        while d.weekday() >= 5:
            d += timedelta(days=1)
        s["open2"] = iso(d)
        s["open2est"] = 1
    if exams:
        terms = {}
        for d, n in exams:
            terms.setdefault("1" if d.month <= 7 else "2", []).append((d, n))
        ex = []
        for t, lst in sorted(terms.items()):
            names = {}
            for d, n in lst:
                names.setdefault(n, []).append(d)
            for n, ds in names.items():
                ex.append([iso(min(ds)), iso(max(ds)), n])
        ex.sort()
        s["exams"] = ex[:6]
    if discs:
        s["disc"] = sorted({iso(d) for d in discs})[:10]
    grad = [d for d, n in kept if re.search(r"(졸업식)", n)]
    if grad:
        s["grad"] = iso(min(grad))
    end = [d for d, n in kept if re.search(r"(종업식|수료식)", n)]
    if end:
        s["end"] = iso(max(end))
    return {"ay": AY, "s": s, "ev": merge_ranges(kept)[:90], "sat": sat}


def work(school):
    rows = fetch_rows(school["ATPT_OFCDC_SC_CODE"], school["SD_SCHUL_CODE"])
    if rows is None:
        return school["SD_SCHUL_CODE"], None
    if not rows:
        return school["SD_SCHUL_CODE"], {}
    return school["SD_SCHUL_CODE"], summarize(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--refresh", action="store_true", help="기존 결과를 무시하고 전체 재수집(완료 시에만 교체)")
    args = ap.parse_args()

    schools = json.load(open(RAW_LIST, encoding="utf-8"))
    if args.limit:
        schools = schools[:args.limit]
    partial = OUT + ".partial"
    prev = {}
    if os.path.exists(OUT):
        prev = json.load(open(OUT, encoding="utf-8"))
    result = {}
    if not args.refresh and not args.limit:
        src = partial if os.path.exists(partial) else OUT
        if os.path.exists(src):
            result = json.load(open(src, encoding="utf-8"))
            if result and next(iter(result.values())).get("ay") != AY:
                result = {}
    todo = [s for s in schools if s["SD_SCHUL_CODE"] not in result]
    print(f"학년도 {AY}: 대상 {len(schools):,}개교, 신규 조회 {len(todo):,}개교", flush=True)

    fail = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(work, s) for s in todo]
        for i, fu in enumerate(as_completed(futs), 1):
            code, rec = fu.result()
            if rec is None:
                fail += 1
            elif rec:
                result[code] = rec
            if i % 500 == 0:
                json.dump(result, open(partial, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
                print(f"  {i:,}/{len(todo):,} (보유 {len(result):,}, 실패 {fail})", flush=True)

    if args.limit:
        print(f"[--limit] 샘플 {len(result)}개교 (저장 안 함)")
        return
    if prev and len(result) < len(prev) * 0.5:
        raise SystemExit(f"수집 {len(result):,}개교가 기존 {len(prev):,}개교의 절반 미만 — API 오류로 보고 저장 중단")
    json.dump(result, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    if os.path.exists(partial):
        os.remove(partial)
    print(f"저장: {OUT} ({len(result):,}개교, 실패 {fail}, {os.path.getsize(OUT)/1e6:.1f}MB)")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
fetch_class_info.py - NEIS 학급정보(classInfo)로 학교별 학년별 학급 수를 수집한다 (학년도 AY 기준, 학교당 학급 행을 세어 집계).
교육청 단위로 1,000행씩 페이징하므로 전국 약 300콜 안팎. 학생 수는 NEIS에 없어 제공하지 않는다.
출력: _rawdata/class_info.json  {학교코드: {"ay": "2026", "d": {"1": 학급수, ...}(주간), "n": {...}(야간·있을 때만)}}
키: 환경변수 NEIS_API_KEY (없으면 로컬 .env 의 NEIS_API_KEY — 코드에 넣지 않는다).
"""
import collections, datetime, json, os, re, sys, time
import requests

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_LIST = os.path.join(ROOT, "_rawdata", "school_list_raw.json")
OUT = os.path.join(ROOT, "_rawdata", "class_info.json")
BASE = "https://open.neis.go.kr/hub/classInfo"

def key():
    k = os.environ.get("NEIS_API_KEY")
    if k: return k
    p = os.path.join(ROOT, ".env")
    if os.path.exists(p):
        m = re.search(r"NEIS_API_KEY\s*=\s*(\S+)", open(p, encoding="utf-8").read())
        if m: return m.group(1).strip("\"'")
    sys.exit("환경변수 NEIS_API_KEY 가 필요합니다.")

def school_year(today=None):
    t = today or datetime.date.today()
    return t.year if t.month >= 3 else t.year - 1

def fetch_school(k, atpt, code, ay, tries=5):
    for a in range(tries):
        try:
            r = requests.get(BASE, params={"KEY": k, "Type": "json", "pIndex": 1, "pSize": 300, "ATPT_OFCDC_SC_CODE": atpt, "SD_SCHUL_CODE": code, "AY": ay}, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status(); j = r.json()
            if "classInfo" in j: return j["classInfo"][1]["row"]
            return []                         # INFO-200 해당 데이터 없음
        except Exception:
            if a == tries - 1: raise
            time.sleep(2 + a)

def main():
    import concurrent.futures
    k = key(); ay = str(school_year())
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 10 ** 9
    schools = [(d["ATPT_OFCDC_SC_CODE"], d["SD_SCHUL_CODE"]) for d in json.load(open(RAW_LIST, encoding="utf-8")) if d.get("ATPT_OFCDC_SC_CODE") and d.get("SD_SCHUL_CODE")]
    out = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    todo = [(a, c) for a, c in schools if out.get(c, {}).get("ay") != ay][:limit]       # 같은 학년도 값이 있으면 건너뜀(학년도가 바뀌면 전부 재수집)
    print("학교", len(schools), "수집됨", len(out), "이번", len(todo), "AY", ay, flush=True)
    def one(t):
        a, c = t
        try: return c, fetch_school(k, a, c, ay), None
        except Exception as e: return c, None, e
    t0 = time.time(); fail = 0
    with concurrent.futures.ThreadPoolExecutor(8) as ex:
        for n, (c, rows, err) in enumerate(ex.map(one, todo), 1):
            if err is not None:
                fail += 1
                if fail > 30: print("오류 과다 중단:", err); break
                continue
            day = collections.Counter(); night = collections.Counter()
            for r in rows: (night if (r.get("DGHT_CRSE_SC_NM") or "").strip() == "야간" else day)[str(r["GRADE"])] += 1
            e = {"ay": ay, "d": dict(sorted(day.items()))}
            if night: e["n"] = dict(sorted(night.items()))
            out[c] = e
            if n % 1000 == 0:
                print("  %d/%d (%.0f초) 오류 %d" % (n, len(todo), time.time() - t0, fail), flush=True)
                json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("완료 학교", len(out), "(학급 있는 학교 %d)" % sum(1 for v in out.values() if v["d"] or v.get("n")), "오류", fail, "(%.0f초)" % (time.time() - t0))

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
process_data.py - 학교 목록 + 점진적으로 쌓이는 급식 데이터를 Jekyll 페이지용 JSON으로 가공

입력:
  _rawdata/school_list_raw.json  - 전국 12,673개 학교 기본정보 (NEIS schoolInfo)
  _rawdata/meal_detail.json      - {SD_SCHUL_CODE: [급식기록...]} 최근 구간, 점진적으로 채워짐
출력:
  _rawdata/schools_{시도}.json   - 시도별 분할
  search_index.json              - 검색용 경량 인덱스 (전체 12,673개)
  _rawdata/stats.json            - 진행 통계
"""
import json, re, hashlib, sys
from pathlib import Path
from collections import defaultdict, Counter

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent.parent
RAW_LIST = ROOT / "_rawdata" / "school_list_raw.json"
RAW_MEAL = ROOT / "_rawdata" / "meal_detail.json"
RAWDATA_DIR = ROOT / "_rawdata"
SEARCH_INDEX_OUT = ROOT / "search_index.json"
STATS_OUT = ROOT / "_rawdata" / "stats.json"

DO_MAP = {
    "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구",
    "인천광역시": "인천", "광주광역시": "광주", "대전광역시": "대전",
    "울산광역시": "울산", "세종특별자치시": "세종", "경기도": "경기",
    "강원특별자치도": "강원", "강원도": "강원",
    "충청북도": "충북", "충청남도": "충남",
    "전북특별자치도": "전북", "전라북도": "전북", "전라남도": "전남",
    "경상북도": "경북", "경상남도": "경남", "제주특별자치도": "제주", "제주도": "제주",
}


def guess_sido(lctn):
    text = (lctn or "").strip()
    if "전남광주통합특별시(전남)" in text:
        return "전남"
    if "전남광주통합특별시(광주)" in text:
        return "광주"
    if text in DO_MAP:
        return DO_MAP[text]
    if text in DO_MAP.values():
        return text
    return ""


def guess_sigungu(addr):
    """도로명주소 2번째 토큰을 시군구로 사용 (예: '서울특별시 송파구 송이로 42' -> '송파구')"""
    if not addr:
        return ""
    parts = addr.strip().split()
    if len(parts) >= 2:
        return parts[1]
    return ""


def slugify(text: str, extra: str) -> str:
    slug = re.sub(r"[^\w가-힣\s-]", "", text).strip()
    slug = re.sub(r"\s+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    h = hashlib.md5((text + "|" + extra).encode("utf-8")).hexdigest()[:6]
    return f"{slug}-{h}" if slug else h


def main():
    raw = json.loads(RAW_LIST.read_text(encoding="utf-8"))
    meal_map = {}
    if RAW_MEAL.exists():
        meal_map = json.loads(RAW_MEAL.read_text(encoding="utf-8"))
    print(f"학교 {len(raw)}건, 급식정보 확보 {len(meal_map)}건 ({len(meal_map)*100//max(len(raw),1)}%)")

    schools = []
    seen_slugs = Counter()
    skipped = 0
    for d in raw:
        code = d.get("SD_SCHUL_CODE")
        name = (d.get("SCHUL_NM") or "").strip()
        do_short = guess_sido(d.get("LCTN_SC_NM"))
        addr = (d.get("ORG_RDNMA") or "").strip()
        sigungu = guess_sigungu(addr) or "기타"
        if not code or not name or not do_short:
            skipped += 1
            continue

        slug = slugify(name, code)
        seen_slugs[slug] += 1
        if seen_slugs[slug] > 1:
            slug = f"{slug}-{seen_slugs[slug]}"

        meals = meal_map.get(code)
        has_meal = meals is not None
        schools.append({
            "code": code,
            "atptCode": d.get("ATPT_OFCDC_SC_CODE"),
            "schoolName": name,
            "kind": d.get("SCHUL_KND_SC_NM") or "",
            "doShort": do_short,
            "sigungu": sigungu,
            "slug": slug,
            "addr": addr,
            "zipcode": (d.get("ORG_RDNZC") or "").strip(),
            "tel": (d.get("ORG_TELNO") or "").strip(),
            "homepage": (d.get("HMPG_ADRES") or "").strip(),
            "coedu": d.get("COEDU_SC_NM") or "",
            "foundType": d.get("FOND_SC_NM") or "",
            "foundYmd": d.get("FOND_YMD") or "",
            "hasMeal": has_meal,
            "meals": meals or [],
        })

    print(f"제외: {skipped}건 (코드/이름/지역 누락)")

    by_do = defaultdict(list)
    for s in schools:
        by_do[s["doShort"]].append(s)

    RAWDATA_DIR.mkdir(parents=True, exist_ok=True)
    for do, group in by_do.items():
        out = RAWDATA_DIR / f"schools_{do}.json"
        out.write_text(json.dumps(group, ensure_ascii=False), encoding="utf-8")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {do}: {len(group)}개 학교 -> {out.name} ({size_mb:.1f}MB)")

    print(f"\n총 {len(schools)}개 학교 저장 (시도 {len(by_do)}개 파일)")

    do_counts = Counter(s["doShort"] for s in schools)
    print("\n지역별 학교 수:")
    for do, cnt in sorted(do_counts.items(), key=lambda x: -x[1]):
        print(f"  {do}: {cnt}개")

    # 검색 인덱스: 전체 12,673개, 경량 필드만
    index = [
        {"n": s["schoolName"], "do": s["doShort"], "sg": s["sigungu"], "s": s["slug"],
         "k": s["kind"], "d": bool(s["hasMeal"])}
        for s in schools
    ]
    SEARCH_INDEX_OUT.write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    size_mb = SEARCH_INDEX_OUT.stat().st_size / 1024 / 1024
    print(f"\n검색 인덱스 {len(index)}개 저장 -> {SEARCH_INDEX_OUT} ({size_mb:.1f}MB)")

    filled = sum(1 for s in schools if s["hasMeal"])
    stats = {"total": len(schools), "mealFilled": filled, "mealPct": round(filled * 100 / max(len(schools), 1), 1)}
    STATS_OUT.write_text(json.dumps(stats, ensure_ascii=False), encoding="utf-8")
    print(f"\n급식정보 진행률: {filled}/{len(schools)} ({stats['mealPct']}%)")


if __name__ == "__main__":
    main()

"""
Steam '직전 주 신작' 수집 스크립트 (GitHub Actions에서 실행).
구글 IP가 막히는 문제를, 안정적인 GitHub 러너 IP에서 Steam을 직접 호출해 우회한다.
결과를 data.json 으로 저장한다 → Apps Script가 그 파일을 읽어 시트에 기록한다.
"""

import json
import re
import time
import datetime
import requests

SEARCH_URL = (
    "https://store.steampowered.com/search/results/"
    "?filter=popularnew&category1=998&cc=us&l=english&json=1&start=0&count=100&infinite=1"
)
HEADERS = {"User-Agent": "Mozilla/5.0"}
MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    start=1)}


def last_week_range(today=None):
    """기준일(기본: 오늘)의 '직전 주'(월~일) 범위를 반환."""
    today = today or datetime.date.today()
    this_monday = today - datetime.timedelta(days=today.weekday())
    start = this_monday - datetime.timedelta(days=7)
    end = this_monday - datetime.timedelta(days=1)
    return start, end


def parse_english_date(s):
    """'10 Jun, 2026' / 'Jun 10, 2026' → date. 일자 없으면 None."""
    mon = re.search(r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec", s)
    day = re.search(r"\b(\d{1,2})\b", s)
    year = re.search(r"\b(20\d{2})\b", s)
    if not (mon and day and year):
        return None
    return datetime.date(int(year.group(1)), MONTHS[mon.group(0)], int(day.group(1)))


def get_new_release_appids():
    """검색 결과에서 'appid + 출시일'을 뽑아 직전 주 출시작만 반환."""
    r = requests.get(SEARCH_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    html = r.json().get("results_html", "")

    start, end = last_week_range()
    print(f"직전 주 범위: {start} ~ {end}")

    ids = []
    for m in re.finditer(r'data-ds-appid="(\d+)"[\s\S]*?search_released[^>]*>([^<]*)<', html):
        appid, date_str = m.group(1), m.group(2).strip()
        d = parse_english_date(date_str)
        if d and start <= d <= end:
            ids.append(appid)
    print(f"직전 주 출시작: {len(ids)}개")
    return ids


def get_game(appid):
    """appdetails로 게임 상세 정보 조회 (429 시 재시도)."""
    url = f"https://store.steampowered.com/api/appdetails?appids={appid}&l=korean"
    for attempt in range(1, 6):
        r = requests.get(url, headers=HEADERS, timeout=30)
        if r.status_code == 200:
            try:
                payload = r.json()[appid]
            except Exception:
                return None
            if not payload.get("success") or payload.get("data", {}).get("type") != "game":
                return None
            d = payload["data"]
            return {
                "appid": appid,
                "name": d.get("name", "N/A"),
                "genres": ", ".join(g["description"] for g in d.get("genres", [])) or "N/A",
                "developers": ", ".join(d.get("developers", [])) or "N/A",
                "publishers": ", ".join(d.get("publishers", [])) or "N/A",
                "languages": re.sub(r"<[^>]*>", "", d.get("supported_languages", "")).strip() or "N/A",
                "price": "무료" if d.get("is_free")
                         else (d.get("price_overview", {}).get("final_formatted") or "가격 정보 없음"),
                "release_date": d.get("release_date", {}).get("date", "N/A"),
                "header_image": d.get("header_image", ""),
            }
        print(f"  appid {appid} 시도 {attempt}/5 실패 (HTTP {r.status_code})")
        time.sleep(2 * attempt)
    return None


def main():
    ids = get_new_release_appids()
    games = []
    for appid in ids:
        g = get_game(appid)
        if g:
            games.append(g)
            print(f"{len(games)}/{len(ids)} 수집: {g['name']}")
        time.sleep(1.5)

    out = {
        "updated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "games": games,
    }
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"완료: {len(games)}개 저장 → data.json")


if __name__ == "__main__":
    main()

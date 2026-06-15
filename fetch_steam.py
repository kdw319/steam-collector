"""
Steam 데이터 수집 스크립트 (GitHub Actions에서 실행).
구글 IP가 막히는 문제를, 안정적인 GitHub 러너 IP에서 Steam을 직접 호출해 우회한다.

출력 2개:
  - data.json        : 직전 주 신작 행 목록 (Apps Script updateNewReleasesFromGitHub 용)
  - appdetails.json  : appid -> 게임 상세 맵 (Apps Script getGameDetails 가 조회)
                       신작 + 최고판매 100 + SteamSpy 2주 의 모든 appid를 커버
"""

import os
import json
import re
import time
import datetime
import requests

TARGET_NEW_RELEASES = 30  # 신작 목표 개수 (부족하면 이전 주까지 거슬러 채움)
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
    mon = re.search(r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec", s)
    day = re.search(r"\b(\d{1,2})\b", s)
    year = re.search(r"\b(20\d{2})\b", s)
    if not (mon and day and year):
        return None
    return datetime.date(int(year.group(1)), MONTHS[mon.group(0)], int(day.group(1)))


def fetch_search_page(start):
    """popularnew 검색 한 페이지(results_html) 가져오기."""
    url = (
        "https://store.steampowered.com/search/results/"
        f"?filter=popularnew&category1=998&cc=us&l=english&json=1&start={start}&count=100&infinite=1"
    )
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        return r.json().get("results_html", "")
    except Exception as e:
        print(f"  검색 페이지 start={start} 실패: {e}")
        return ""


def get_new_release_appids():
    """직전 주 끝(지난 일요일) 이전에 출시된 게임을 최신순으로 최대 TARGET개 반환.
    직전 주만으로 부족하면 그 이전 주들까지 자동으로 거슬러 올라가 채운다."""
    _, end = last_week_range()  # 직전 주 일요일
    print(f"기준: {end} 이전 출시작 중 최신순 최대 {TARGET_NEW_RELEASES}개")

    seen = set()
    candidates = []  # (date, appid)
    for start in (0, 100, 200):  # 최대 300개 후보 풀
        html = fetch_search_page(start)
        if not html:
            continue
        for m in re.finditer(r'data-ds-appid="(\d+)"[\s\S]*?search_released[^>]*>([^<]*)<', html):
            appid, date_str = m.group(1), m.group(2).strip()
            if appid in seen:
                continue
            d = parse_english_date(date_str)
            if d and d <= end:  # 직전 주 끝 이전(=이미 출시된 것)
                seen.add(appid)
                candidates.append((d, appid))
        time.sleep(1.0)

    candidates.sort(key=lambda x: x[0], reverse=True)  # 최신순
    chosen = candidates[:TARGET_NEW_RELEASES]
    ids = [appid for _, appid in chosen]
    if chosen:
        print(f"후보 {len(candidates)}개 중 최신 {len(ids)}개 선정 ({chosen[0][0]} ~ {chosen[-1][0]})")
    else:
        print("후보 없음")
    return ids


def get_top_seller_appids():
    """games-popularity 에서 최고 판매 100위 appid 목록."""
    key = os.environ.get("GAMES_POPULARITY_KEY", "")
    url = f"https://games-popularity.com/swagger/api/top-sellers?apiKey={key}"
    try:
        r = requests.get(url, headers={"accept": "*/*"}, timeout=30)
        data = r.json().get("data", [])
        ids = []
        for x in data:
            pos = x.get("position", 0)
            sid = x.get("steamId")
            if sid and 0 < pos <= 100:
                ids.append(str(sid))
        print(f"최고 판매 appid: {len(ids)}개")
        return list(dict.fromkeys(ids))
    except Exception as e:
        print(f"top-sellers 실패: {e}")
        return []


def get_steamspy_appids():
    """SteamSpy 최근 2주 인기 appid 목록."""
    try:
        r = requests.get("https://steamspy.com/api.php?request=top100in2weeks", timeout=30)
        ids = [str(k) for k in r.json().keys()]
        print(f"SteamSpy appid: {len(ids)}개")
        return ids
    except Exception as e:
        print(f"steamspy 실패: {e}")
        return []


def get_game(appid):
    """appdetails로 게임 상세 정보 조회 (429 시 재시도)."""
    url = f"https://store.steampowered.com/api/appdetails?appids={appid}&l=korean"
    for attempt in range(1, 6):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
        except Exception as e:
            print(f"  appid {appid} 시도 {attempt}/5 예외: {e}")
            time.sleep(2 * attempt)
            continue
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
    new_ids = get_new_release_appids()
    top_ids = get_top_seller_appids()
    spy_ids = get_steamspy_appids()

    all_ids = list(dict.fromkeys(new_ids + top_ids + spy_ids))  # 순서 유지 + 중복 제거
    print(f"전체 상세조회 대상: {len(all_ids)}개")

    details = {}
    for i, appid in enumerate(all_ids, 1):
        g = get_game(appid)
        if g:
            details[appid] = g
        if i % 20 == 0:
            print(f"  진행 {i}/{len(all_ids)} (성공 {len(details)})")
        time.sleep(1.2)

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # 1) 신작 시트용 (기존 형식 유지)
    new_games = [details[i] for i in new_ids if i in details]
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump({"updated": now, "games": new_games}, f, ensure_ascii=False, indent=2)

    # 2) 상세 정보 맵 (Apps Script getGameDetails 가 조회)
    with open("appdetails.json", "w", encoding="utf-8") as f:
        json.dump({"updated": now, "details": details}, f, ensure_ascii=False, indent=2)

    print(f"완료: 신작 {len(new_games)}개 / 상세맵 {len(details)}개 저장")


if __name__ == "__main__":
    main()

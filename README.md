# Steam 직전 주 신작 수집기

구글 Apps Script가 Steam에 접속하지 못하는(IP 차단) 문제를, 안정적인 GitHub Actions IP에서
Steam을 직접 호출해 우회한다.

## 구조

```
GitHub Actions (주 1회 + 수동)  →  Steam 직접 호출  →  data.json 커밋
                                                          │
Apps Script (기존)  ←  raw.githubusercontent 의 data.json 읽기  →  시트 기록
```

## 설치 (한 번만)

1. GitHub에서 새 저장소(repo) 생성 — 이름 예: `steam-collector` (private 가능)
2. 이 폴더의 파일들을 그 repo에 업로드:
   - `fetch_steam.py`
   - `.github/workflows/collect.yml`
   - `README.md` (선택)
3. repo의 **Actions** 탭 → 워크플로우 선택 → **Run workflow** 로 수동 실행 테스트
4. 실행이 끝나면 repo에 `data.json` 이 생긴다. 그 파일의 **Raw** 버튼을 눌러 주소를 복사:
   `https://raw.githubusercontent.com/<USER>/<REPO>/main/data.json`
5. Apps Script에 `updateNewReleasesFromGitHub()` 함수를 추가하고(채팅 참고),
   `GITHUB_DATA_URL` 을 위 주소로 바꾼 뒤 실행.

## 참고
- 자동 실행 주기는 `collect.yml` 의 `cron` 한 줄로 조절한다. (현재: 매주 월요일)
- `raw.githubusercontent` 는 약 5분 캐시가 있어, 갓 커밋된 내용이 잠깐 늦게 보일 수 있다.

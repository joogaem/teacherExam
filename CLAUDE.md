# 임용고시 RAG 퀴즈 플랫폼

설보연 교육학 교재 기반 문제 생성·풀이 개인 학습 플랫폼. 상세한 구조·의사결정 기록은 [docs/analysis-report.md](docs/analysis-report.md) 참고.

## 구조

- `backend/` — FastAPI (Python 3.12, venv: `.venv`). 실행: `.venv/Scripts/python.exe main.py` (로컬 :8000)
- `frontend/` — Next.js 16 + React 19. 실행: `npm run dev` (:3000)
- `supabase/` — DB 스키마 SQL (Supabase SQL Editor에서 수동 실행)
- DB는 **공유 Supabase 프로젝트** — 모든 컴퓨터·서버가 같은 데이터를 봄. 코드만 git으로 동기화
- `backend/.env` — API 키 (git 제외, 컴퓨터마다 수동 복사): SUPABASE_URL/SERVICE_KEY, ANTHROPIC_API_KEY, VOYAGE_API_KEY

## 운영 서버 (AWS Lightsail) — 2026-07-08 구조 개편

- 접속: **https://joogaem-quiz.duckdns.org** (2026-08-10 HTTPS 전환. Let's Encrypt, 3개 도메인 SAN 1장, 자동 갱신).
  - 기기 등록: `/trust` 를 한 번 방문하면 1년짜리 `quizauth` 쿠키가 심어져 이후 Basic Auth 프롬프트가 안 뜬다. 쿠키가 없으면 기존대로 Basic Auth(로그인 정보는 사용자 `Documents\lightsail-basic-auth.txt`).
  - 같은 서버의 다른 앱: `joogaem-eat`(eatNwrite+자기관리기록), `joogaem-focus`(뽀모도로) — 전부 `.duckdns.org`
  - 구주소 http://43.202.142.135:8001 및 :3000은 **아직 살아 있음**(이관 확인 후 정리 예정)
  - 전환 절차·실전 함정은 [docs/HTTPS_SETUP.md](docs/HTTPS_SETUP.md). nginx는 **1.18.0**이라 `http2 on;`(1.25.1+) 문법 쓰면 안 뜬다.
- 구조: nginx(:8001)가 정적 프론트(`/var/www/quiz`) 직접 서빙 + `/api/*`만 백엔드(127.0.0.1:8011, 내부 전용)로 프록시. **nginx가 `/api` 접두사를 벗겨 전달하므로 백엔드 라우트는 prefix 없이 그대로.**
- systemd 서비스: `quiz-backend`만 (자동 재시작). ~~quiz-frontend~~ Next 서버는 폐지됨.
- 재배포:
  - 백엔드: 서버에서 `git pull` + `sudo systemctl restart quiz-backend`
  - 프론트: 로컬에서 `NEXT_PUBLIC_API_URL=/api`로 `next build` → `out/`을 tar→scp→서버 `/var/www/quiz`에 전개(`--strip-components=1`). **서버 빌드·Next 서버·standalone 절차 전부 폐지.**
  - ⚠️ **빌드는 반드시 PowerShell에서** (`$env:NEXT_PUBLIC_API_URL="/api"; npx next build`). Git Bash로 하면 MSYS 경로 변환이 `/api`를 `C:/Program Files/Git/api`로 바꿔 번들에 박아버려 전 API 호출이 `file:///C:/...`로 나간다 (2026-08-10 실제 발생).
  - 배포 후 검증: 번들에 `"/api"`가 있고 `Program Files`가 없어야 한다 — `grep -rl '"/api"' out/_next/static/chunks/` / `grep -r "Program Files" out/_next/static/chunks/`
- **1GB RAM이라 서버에서 npm install/build 절대 금지** (OOM으로 SSH까지 마비됨) — 정적 export 전환으로 서버 빌드 자체가 불필요해짐
- schedulingBot은 2026-07-07 제거됨(포트 8000 비어 있음). pm2도 제거(전부 systemd).
- SSH 키: `LightsailDefaultKey-ap-northeast-2.pem` (git 제외) 또는 PC의 `~/.ssh/id_ed25519` (2026-07-07 등록)

## 핵심 도메인 지식

- **강의 체계**: 본강 76강 + 마이너특강 7강 = 78강 (`lectures` 테이블). 1~48강 → 1권, 49강~ → 2권
- **페이지 보정**: 교재 인쇄 페이지 ≠ PDF 페이지. `seed_lectures.py`의 ANCHORS로 선형 보간 (`printed_to_pdf()`)
- **검색**: `match_chunks_pages()` — 페이지 윈도우(±25→±60→±150 점진 확장) + 시맨틱.
  pgvector ivfflat은 book_id 필터와 결합 시 recall 구멍 → SQL 함수에 `enable_indexscan=off` 적용됨
- **문제 생성**: 전 유형 1회 통합 호출 (`generate_questions_multi`) — 유형별 호출 금지 (토큰 중복)
- **chunks 소스 구분**: chapter prefix — 교재 원문(일반 챕터명) vs `[필기노트] ...`
- **questions 출처 구분**: chapter prefix `[형성평가] ...` = 실제 강사 문제 (474문항, 강의 매핑됨)

## 강의 자료 임포트 (classPdfs/ — git 제외, 저작권 자료)

- `import_assessments.py` — 형성평가 해설편 → 문제은행 (이어하기 모드, `--force` 재임포트) ✅ 완료
- `import_notes.py` — 필기노트 → chunks 검색 소스 ✅ 완료
- 개념TREE (이미지 PDF, 비전 추출 필요) — 미착수

## 게임 모드 (/game)

- 78강 도장깨기: 객관식3(잡몹) → 빈칸2·짝맞추기1(중간보스) → 서술형1(보스, 60점 이상 격파)
- 목숨 3개, 콤보 배율(최대 ×2), 유형별 타이머. 진행도: `lecture_progress` 테이블
- Phaser 전투 씬 (`components/game/Battle.tsx`) — useEffect 안에서 동적 import (SSR 회피)

## 주의사항

- frontend는 Next.js 16 — AGENTS.md 경고대로 학습데이터와 API가 다를 수 있음, `node_modules/next/dist/docs/` 참고
- 퀴즈/게임 문제 컴포넌트는 내부 상태를 가짐 — 렌더링 시 반드시 `key={question.id}` (없으면 이전 선택 잔존 버그)
- Windows 콘솔 cp949 — 파이썬 스크립트는 `sys.stdout.reconfigure(encoding="utf-8")` 필요

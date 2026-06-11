# 임용고시 RAG 퀴즈 플랫폼 — 구축·확장·배포 분석 보고서

> 작성일: 2026-06-11
> 저장소: https://github.com/joogaem/teacherExam

---

## 1. 프로젝트 개요

설보연 교육학 교재(2권, 총 ~1,600페이지 PDF)를 RAG로 구축하여, 임용고시 수준의 문제를 자동 생성·채점하는 개인용 학습 플랫폼.

| 구분 | 기술 |
|---|---|
| 백엔드 | FastAPI + uvicorn (Python 3.12) |
| 프론트엔드 | Next.js 16 + React 19 + Tailwind |
| DB | Supabase (PostgreSQL + pgvector) |
| 임베딩 | Voyage AI `voyage-3` (1024차원) |
| 문제 생성·채점 | Claude `claude-sonnet-4-5` |
| 복습 알고리즘 | SM-2 (Spaced Repetition) |

### RAG 파이프라인

```
PDF → PyMuPDF 텍스트 추출 → 청킹 → Voyage 임베딩 → Supabase pgvector
                                                          ↓
사용자 요청 → 벡터 유사도 검색(top-k) → Claude 문제 생성 → 풀이/채점 → SR 카드 갱신
```

### DB 스키마 (핵심 테이블)

- `books` — 교재 메타데이터
- `chunks` — 텍스트 청크 + 1024차원 임베딩 (ivfflat 인덱스)
- `lectures` — **(신규)** 78강 커리큘럼 (강번호·주차·PART·제목·페이지 범위)
- `questions` — 생성된 문제 (JSONB) + `lecture_id` 태그 **(신규)**
- `quiz_sessions` / `user_answers` — 풀이 세션·답안 기록
- `sr_cards` — SM-2 복습 스케줄

Supabase는 두 컴퓨터가 **공유하는 단일 프로젝트** — 코드만 깃으로 동기화하고 데이터는 공유.

---

## 2. 이번 작업 내역

### 2-1. 환경 복제 (다른 PC → 이 PC)

- GitHub에서 클론 후 백엔드 venv, 프론트 npm 환경 재구성
- `.env`(API 키)는 깃 제외 — 수동 복사
- `check_setup.py` 작성: 환경변수 4종 + Supabase/Voyage/Anthropic 연결 자가진단

### 2-2. 강의별 문제풀기 기능 (78강 커리큘럼)

**스키마 (추가만, 기존 테이블 무손상)**
- `lectures` 테이블 신설: 본강 76강 + 마이너특강 7강 중 78강 시딩
- `questions.lecture_id` 컬럼 추가 → 강의별 문제은행 조회 가능

**페이지 오프셋 보정**
- 교재 인쇄 페이지 ≠ PDF 페이지. 앵커 포인트를 실측해 선형 보간으로 변환
  - 1권: `(16,17) (68,70) (276,281) (424,430)` — 오프셋이 점점 커지는 패턴
  - 2권: `(16,16) (284,281) (448,448) ...` — 거의 0

**하이브리드 검색 (강의 → 청크)**
- 페이지 윈도우를 점진 확장(±25 → ±60 → ±150)하며 시맨틱 검색
- 최소 3개 미달 시 전권 검색 폴백
- 효과: 같은 주제가 여러 PART에 등장해도(예: 동기이론 — 교육행정 강56 vs 교육심리 강71) 페이지 윈도우로 정확히 분리

**API**
- `GET /books/{book_id}/lectures` — 강의 목록
- `POST /questions/generate` — `lecture_id` 지원
- `GET /lectures/{id}/questions` — 강의 문제은행 조회
- `POST /lectures/{id}/prebuild` — 문제은행 사전 생성

**프론트**
- 강의별/챕터별 모드 토글, PART별 `<optgroup>` 강의 선택
- "문제 생성 시작 / 저장된 문제로 풀기 / 미리 만들기" 3버튼

### 2-3. 성능·토큰 최적화

**통합 생성 (`generate_questions_multi`)**
- 기존: 유형(객관식/빈칸/짝맞추기/서술형)마다 Claude 호출 → 교재 컨텍스트가 유형 수만큼 중복 전송
- 개선: **전 유형을 1회 호출로 생성** — 컨텍스트 토큰 1/N, 지연시간 1/N
- 문제 저장도 개별 insert → **배치 insert**로 변경

### 2-4. 해결한 버그

| 버그 | 원인 | 해결 |
|---|---|---|
| 특정 강의 검색 0건 | pgvector ivfflat 근사검색이 `book_id` 필터와 결합 시 recall 구멍 | SQL 함수에 `set enable_indexscan=off` (청크 수가 적어 정밀검색으로 충분) |
| `ivfflat.probes` 설정 불가 | Supabase 권한 제한 (42501) | 위 방식으로 우회 |
| JSON 파싱 실패 | Claude가 설명문을 섞어 응답 | `_parse_json()` — 코드펜스 제거 + 괄호 범위 추출 폴백 |
| 강3·강4 누락 (76/78) | 페이지 정규식이 `p.16~19` 형식 미지원 | `PAGE_RE` 패턴 확장 |
| 강15 타일러 오답 검색 | 해당 페이지 청크 희소 → 전권 폴백이 다른 PART의 타일러 반환 | 점진 윈도우 확장(±60에서 정답 포착) |
| 콘솔 인코딩 에러 | Windows cp949 | `sys.stdout.reconfigure(encoding="utf-8")` |

---

## 3. 서버 배포 (AWS Lightsail)

### 3-1. 핵심 제약과 해법

**제약**: 1GB RAM 인스턴스 — `npm run build`(~1GB), `npm install`(수백 MB)을 서버에서 실행하면 OOM으로 SSH까지 먹통 (실제 2회 발생, 재부팅 필요했음)

**해법**: 서버에서 무거운 작업 0개
1. 로컬 PC에서 `output: "standalone"` 모드로 빌드
2. 필요 파일만 묶은 **3.5MB tar.gz** 업로드
3. 서버는 `node server.js` 실행만 — `npm install` 불필요
4. PM2 대신 **systemd** — 추가 설치 없음, 부팅 시 자동 시작, 죽으면 5초 후 자동 재시작
5. 스왑 2GB 추가 (`/etc/fstab` 등록, 재부팅에도 유지) — 보험용

### 3-2. 배포 구조

```
[어디서든 브라우저]
       │  http://43.202.142.135:3000
       ▼
┌─ Lightsail (1GB RAM, Ubuntu) ─────────────────┐
│  quiz-frontend  : Next standalone :3000  77MB │
│  quiz-backend   : uvicorn         :8001 146MB │
│  (기존) schedulingbot      :8000               │
│  (기존) eatnwrite-backend  :3001               │
│  (기존) unifiedbot         (디스코드 전용)      │
└────────────────────────────────────────────────┘
       │                    │
       ▼                    ▼
   Supabase            Claude / Voyage API
  (pgvector)            (문제 생성·임베딩)
```

- 퀴즈 백엔드는 8001 사용 — 8000은 기존 schedulingBot이 선점
- 실제 무거운 연산(생성·임베딩)은 전부 외부 API → 서버는 중계만

### 3-3. 배포 후 리소스 측정

| 항목 | 측정값 | 평가 |
|---|---|---|
| RAM | 443MB / 913MB 사용, 스왑 사용 0 | 여유 — 스왑을 안 쓴다는 것이 메모리 무압박의 증거 |
| 퀴즈 앱 몫 | ~220MB (백엔드 146 + 프론트 77) | 예상치(250MB) 이내 |
| CPU | load average 0.00 | 유휴 — 요청 시에만 동작 |
| 디스크 | 9.8GB / 39GB (26%) | 여유 |
| 기존 서비스 영향 | 봇 3종 정상 동작 | 충돌 없음 |

### 3-4. 재배포 절차 (코드 수정 시)

```powershell
# 로컬 PC
cd D:\teacherExam\frontend
$env:NEXT_PUBLIC_API_URL="http://43.202.142.135:8001"
npm run build
Copy-Item -Recurse -Force public .next\standalone\public
Copy-Item -Recurse -Force .next\static .next\standalone\.next\static
cd .next; tar -czf ..\..\standalone.tar.gz standalone

# 업로드 + 적용
scp -i key.pem standalone.tar.gz ubuntu@43.202.142.135:/home/ubuntu/workspace/teacherExam/
ssh -i key.pem ubuntu@43.202.142.135 "cd workspace/teacherExam && rm -rf frontend-standalone && mkdir frontend-standalone && tar -xzf standalone.tar.gz -C frontend-standalone --strip-components=1 && sudo systemctl restart quiz-frontend"

# 백엔드만 수정한 경우
ssh -i key.pem ubuntu@43.202.142.135 "cd workspace/teacherExam && git pull && sudo systemctl restart quiz-backend"
```

---

## 4. 아키텍처 효율성 평가

### 잘된 점
- **토큰 효율**: 통합 생성으로 동일 컨텍스트의 중복 전송 제거 (유형 4개 기준 입력 토큰 ~1/4)
- **응답 속도**: API 호출 4회 → 1회, insert N회 → 1회
- **검색 정확도**: 페이지 윈도우 + 시맨틱의 하이브리드로 PART 중복 주제 분리
- **서버 비용**: 기존 인스턴스에 합승 — 추가 비용 0원
- **운영 안정성**: systemd 자동 재시작 + 스왑 보험 + 로컬 빌드 분리

### 한계와 트레이드오프 (1인 사용 전제로 수용)
- `enable_indexscan=off`: 청크 수가 커지면(수십만+) 정밀검색이 느려질 수 있음 — 현재 규모(수천)에선 무관
- HTTP 평문 통신: 도메인이 없어 HTTPS 미적용 — 개인 학습용으로 수용, 추후 도메인 연결 시 Caddy/nginx + Let's Encrypt 권장
- 인증 없음: URL을 아는 사람은 접속 가능 — API 키는 서버에만 있어 유출 위험은 낮음
- 단일 서버: 백업은 Supabase가 담당 (데이터는 서버에 없음)

---

## 5. 접속 정보 요약

| 용도 | 주소 |
|---|---|
| **문제 풀기 (메인)** | http://43.202.142.135:3000 |
| 백엔드 API | http://43.202.142.135:8001 |
| API 문서 (자동생성) | http://43.202.142.135:8001/docs |

서버 상태 확인: `ssh -i key.pem ubuntu@43.202.142.135 "systemctl status quiz-backend quiz-frontend"`

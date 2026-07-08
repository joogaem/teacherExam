# 구현 세션 킥오프 문서 (구현 모델에게 이 문서를 첫 메시지로 줄 것)

너는 `C:\Users\ssduw\workspace\study-app` (FastAPI + Next.js + Supabase) 임용고시 학습 플랫폼의 Phase 1 개선을 구현한다.

## 반드시 먼저 읽을 것 (순서대로)
1. `docs/PHASE1_SPEC.md` — **이번 작업의 유일한 요구사항 문서.** 스키마·API·화면·수용 기준 전부 여기 있음.
2. `C:\Users\ssduw\workspace\teacherExam-backend-analysis.md` — 기존 코드의 알려진 버그 목록. 스펙 §6이 이 중 2건의 수정을 포함.
3. `frontend/AGENTS.md` — **이 repo의 Next.js는 훈련 데이터와 다를 수 있음.** 프론트 코드 작성 전 `node_modules/next/dist/docs/`의 해당 가이드 확인 필수.
4. `C:\Users\ssduw\workspace\아키텍처_효율성_분석.md` — 서버(1GB RAM) 제약과 인프라 방향. 특히: 프론트는 **정적 export + nginx 서빙** 방향이므로 SSR/route handler에 의존하는 구현 금지, 서버 측 문제 생성은 메모리·블로킹을 의식할 것(§1).

## 환경 사실 (2026-07-08 인프라 통합 반영)
- **프론트는 정적 export로 이미 전환됨**: `next.config.ts`에 `output: 'export'` 적용, nginx가 `/var/www/quiz`에서 직접 서빙. **Next 서버는 더 이상 없음** — SSR/route handler/next server 기능에 의존하는 코드 작성 금지.
- **API는 same-origin `/api` 경로**: nginx가 `/api/`를 백엔드(127.0.0.1:8011)로 프록시하며 접두사를 벗겨서 전달 — 백엔드 라우트는 `/api` prefix 없이 그대로. 프론트 빌드 시 `NEXT_PUBLIC_API_URL=/api` 필수.
- **배포 절차**: 로컬 `next build` → `out/`을 tar/scp → 서버 `/var/www/quiz`에 전개. 서버에서 npm 빌드 금지(과거 OOM 원인).

- Windows 11 로컬 개발. 백엔드 실행: `cd backend && python main.py`. 프론트: `cd frontend && node node_modules/next/dist/bin/next dev` (Windows에서 npm 직접 실행이 안 될 수 있음).
- 배포: AWS Lightsail (이 폴더가 배포본과 동일). `.env`는 `backend/.env`에 이미 존재 (Supabase SERVICE_KEY / Anthropic / Voyage).
- Supabase에 실데이터 있음: books 2, chunks 2,934, questions 690, user_answers 131, sr_cards 127. **파괴적 마이그레이션 금지** — 스펙 §8-1의 보존 규칙을 따를 것.
- 스키마 변경은 `supabase/schema.sql`에 반영하되, 실제 적용은 별도 마이그레이션 SQL 파일(`supabase/migrations/`)로 작성해 사용자가 Supabase SQL Editor에서 실행하게 할 것.

## 작업 규칙
- 구현 순서는 스펙 §8-3을 따른다: ① 스키마+사면+채점 엄격화 → ② 오늘의 복습 홈 → ③ 교과교육학 트랙 → ④ 기출 문제은행 → ⑤ 사다리·검수함·약점 화면.
- 각 단계 완료 시 스펙 §8-2 수용 기준 중 해당 항목을 실제로 실행해 검증하고 결과를 보고할 것.
- 스펙 §0-2의 UX 하드 규칙 5개(밀림 수 노출 금지, 스트릭 금지, 일일 상한, 아침 결정 제로, 종료 화면 성취만)는 협상 불가. 애매하면 규칙 쪽으로 해석.
- 보안 하드닝(인증, CORS, RLS)은 이번 범위 아님 — 기존 동작을 악화시키지만 말 것.
- 기출 모범답안(스펙 §2-2)을 작성할 때는 반드시 `answer_verified=false`로 저장하고, 확신 없는 답에 임의 확정 금지. 교과교육 문항의 답안 초안은 `C:\Users\ssduw\workspace\기출분석\교과교육학_프리테스트.md`에 신뢰도 표기와 함께 이미 있음 — 그대로 가져오되 ⚠️/❓ 표기를 유지할 것.
- 기출 원자료: `C:\Users\ssduw\workspace\기출분석\` (텍스트 추출본 3개 + 전공B PDF 4개). 전공A PDF는 OneDrive 바탕화면 폴더. PDF 텍스트 추출은 fitz(PyMuPDF) 사용 — 수식 글리프가 깨지는 부분은 해당 영역을 clip해 PNG 렌더(배율 3x).

## 하지 말 것
- 새 단독 HTML 도구 생성 (모든 기능은 study-app 안으로).
- mcq/matching을 기본 생성 유형에 유지하는 것 (스펙 §5-1: stage 1 요청 시에만).
- 임의의 게이미피케이션 추가 (스트릭, 뱃지, 랭킹 등 — §0-2 근거로 전부 금지).

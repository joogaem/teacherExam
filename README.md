# 임용고시 퀴즈 플랫폼

교육학 교재 PDF 기반 AI 문제 생성 + 스페이스드 리피티션 플랫폼

## 필요한 것

- Python 3.11+
- Node.js 18+
- Supabase 프로젝트 (pgvector 활성화)
- Anthropic API 키
- Voyage AI API 키

## 설치

### 1. 백엔드

```bash
cd backend
pip install -r requirements.txt
```

`.env` 파일 생성:

```
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_SERVICE_KEY=eyJ...
ANTHROPIC_API_KEY=sk-ant-...
VOYAGE_API_KEY=pa-...
```

### 2. DB 스키마

Supabase SQL Editor에서 `supabase/schema.sql` 실행

### 3. 프론트엔드

```bash
cd frontend
npm install
```

## 실행

```bash
# 백엔드 (터미널 1)
cd backend
python main.py

# 프론트엔드 (터미널 2)
cd frontend
node node_modules/next/dist/bin/next dev
```

접속: http://localhost:3000

## PDF 임베딩 (최초 1회)

```bash
cd backend
python ingest_once.py "..\pdfs\book.pdf" "교재 제목"
```

pdfs/ 폴더는 .gitignore에 포함되어 있으므로 별도로 복사해야 합니다.

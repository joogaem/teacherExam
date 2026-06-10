"""
환경 점검 스크립트 — .env 채운 뒤 실행: python check_setup.py
DB 연결 / 기존 교재 데이터 / API 키 유효성을 한 번에 확인한다.
"""
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from dotenv import load_dotenv

load_dotenv()

ok = True

def check(name, cond, detail=""):
    global ok
    mark = "OK " if cond else "FAIL"
    print(f"[{mark}] {name}" + (f" - {detail}" if detail else ""))
    if not cond:
        ok = False

# 1. 환경변수 존재 확인
for var in ["SUPABASE_URL", "SUPABASE_SERVICE_KEY", "ANTHROPIC_API_KEY", "VOYAGE_API_KEY"]:
    val = os.environ.get(var, "")
    placeholder = val in ("", "https://xxxx.supabase.co") or val.endswith("...")
    check(f"{var} 설정됨", bool(val) and not placeholder,
          "비어있거나 예시값 그대로" if placeholder else "")

if not ok:
    print("\n.env 값을 먼저 채워주세요.")
    sys.exit(1)

# 2. Supabase 연결 + 기존 데이터 확인
try:
    from db import get_client
    db = get_client()
    books = db.table("books").select("*").execute().data
    check("Supabase 연결", True)
    check("교재(books) 데이터 존재", len(books) > 0, f"{len(books)}권")
    for b in books:
        cnt = db.table("chunks").select("id", count="exact").eq("book_id", b["id"]).execute().count
        print(f"       - {b['title']}: 청크 {cnt}개")
    qcnt = db.table("questions").select("id", count="exact").execute().count
    print(f"       - 저장된 문제: {qcnt}개")
except Exception as e:
    check("Supabase 연결", False, str(e)[:200])

# 3. Voyage 임베딩 키 확인 (짧은 호출)
try:
    import voyageai
    v = voyageai.Client(api_key=os.environ["VOYAGE_API_KEY"])
    r = v.embed(["연결 테스트"], model="voyage-3", input_type="query")
    check("Voyage API 키", len(r.embeddings[0]) == 1024, f"{len(r.embeddings[0])}차원")
except Exception as e:
    check("Voyage API 키", False, str(e)[:200])

# 4. Anthropic 키 확인 (짧은 호출)
try:
    import anthropic
    c = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    m = c.messages.create(model="claude-sonnet-4-5", max_tokens=8,
                          messages=[{"role": "user", "content": "say ok"}])
    check("Anthropic API 키", bool(m.content), m.content[0].text.strip()[:20])
except Exception as e:
    check("Anthropic API 키", False, str(e)[:200])

print("\n" + ("모든 점검 통과 — 서버를 실행하세요." if ok else "위 FAIL 항목을 확인하세요."))
sys.exit(0 if ok else 1)

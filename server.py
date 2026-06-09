import json
import re
import os
from datetime import datetime, timezone
from pathlib import Path

import fitz  # pymupdf
import uvicorn
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = Path("study_db.json")
NOTES_DIR = Path("notes")


def load_db() -> list:
    if not DB_PATH.exists():
        return []
    return json.loads(DB_PATH.read_text(encoding="utf-8"))


def save_db(data: list):
    DB_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "", name)


@app.get("/")
async def serve_html():
    return FileResponse(Path(__file__).parent / "study_quiz.html", media_type="text/html")


@app.post("/parse")
async def parse_pdf(file: UploadFile = File(...)):
    contents = await file.read()
    try:
        doc = fitz.open(stream=contents, filetype="pdf")
    except Exception:
        raise HTTPException(status_code=400, detail="PDF 파일을 열 수 없습니다.")

    pages_text = []
    for page in doc:
        text = page.get_text().strip()
        if text:
            pages_text.append(text)

    if not pages_text:
        raise HTTPException(
            status_code=400,
            detail="텍스트를 추출할 수 없는 PDF입니다 (스캔본의 경우 OCR이 필요합니다)",
        )

    return {
        "text": "\n\n---\n\n".join(pages_text),
        "pages": len(pages_text),
        "filename": file.filename,
    }


class SaveRequest(BaseModel):
    id: str
    subject: str
    date: str
    content: str
    summary: str


@app.post("/save")
async def save_item(req: SaveRequest):
    db = load_db()

    now = datetime.now(timezone.utc).isoformat()
    item = {
        "id": req.id,
        "subject": req.subject,
        "date": req.date,
        "content": req.content,
        "summary": req.summary,
        "createdAt": now,
    }

    idx = next((i for i, x in enumerate(db) if x["id"] == req.id), None)
    if idx is not None:
        item["createdAt"] = db[idx].get("createdAt", now)
        db[idx] = item
    else:
        db.insert(0, item)

    save_db(db)

    NOTES_DIR.mkdir(exist_ok=True)
    safe_subject = sanitize_filename(req.subject)
    md_filename = f"{req.date}_{safe_subject}.md"
    md_path = NOTES_DIR / md_filename

    md_content = f"""---
date: {req.date}
subject: {req.subject}
id: {req.id}
---

# {req.subject} — {req.date}

## 요약

{req.summary}

## 원본 내용

{req.content}
"""
    md_path.write_text(md_content, encoding="utf-8")

    return {"ok": True, "md_path": str(md_path)}


@app.get("/db")
async def get_db():
    return load_db()


@app.delete("/db/{item_id}")
async def delete_item(item_id: str):
    db = load_db()
    db = [x for x in db if x["id"] != item_id]
    save_db(db)
    return {"ok": True}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

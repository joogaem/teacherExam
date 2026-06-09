"""
PDF 1회 임베딩 스크립트
사용법: python ingest_once.py "교재파일.pdf" "교재 제목"
"""

import sys
from pathlib import Path
from ingestion import ingest_pdf, get_chapters

def main():
    if len(sys.argv) < 3:
        print("사용법: python ingest_once.py <pdf경로> <교재제목>")
        sys.exit(1)

    pdf_path = Path(sys.argv[1])
    title = sys.argv[2]

    if not pdf_path.exists():
        print(f"파일을 찾을 수 없습니다: {pdf_path}")
        sys.exit(1)

    print(f"[*] {title} 임베딩 시작...")
    print(f"   파일 크기: {pdf_path.stat().st_size / 1024 / 1024:.1f}MB")

    pdf_bytes = pdf_path.read_bytes()
    book_id = ingest_pdf(pdf_bytes, pdf_path.name, title)

    chapters = get_chapters(book_id)
    print(f"\n[완료]")
    print(f"   book_id: {book_id}")
    print(f"   감지된 챕터 수: {len(chapters)}")
    print(f"\n챕터 목록:")
    for i, ch in enumerate(chapters, 1):
        print(f"  {i:2d}. {ch}")

if __name__ == "__main__":
    main()

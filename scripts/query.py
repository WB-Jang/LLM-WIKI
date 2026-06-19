#!/usr/bin/env python3
"""Query the LLM-Wiki.

Usage:
  python -m scripts.query "질문 내용"
  poetry run query "질문 내용"
"""

import sys
import argparse
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from scripts.config import get_client, wiki_dir

MAX_PAGES = 5
MAX_PAGE_CHARS = 3_000


def _list_pages(wdir: Path) -> list[dict]:
    pages = []
    for md in wdir.rglob("*.md"):
        if md.name in ("index.md", "log.md"):
            continue
        rel = md.relative_to(wdir)
        pages.append({
            "path": str(rel),
            "name": md.stem,
            "preview": md.read_text("utf-8")[:200],
        })
    return pages


def _select_pages(client, cfg, question: str, pages: list[dict]) -> list[str]:
    if not pages:
        return []
    catalog = "\n".join(
        f"{i + 1}. [{p['name']}] ({p['path']})\n   {p['preview'][:120]}..."
        for i, p in enumerate(pages[:50])
    )
    resp = client.chat.completions.create(
        model=cfg["model"],
        messages=[{
            "role": "user",
            "content": (
                f"다음 질문에 답하기 위해 가장 관련성 높은 위키 페이지를 최대 {MAX_PAGES}개 선택하세요.\n\n"
                f"질문: {question}\n\n"
                f"위키 페이지 목록:\n{catalog}\n\n"
                f"관련 페이지 번호만 쉼표로 출력하세요. 예: 1,3,5"
            ),
        }],
        temperature=0,
        max_tokens=30,
    )
    selected = []
    for part in resp.choices[0].message.content.split(","):
        try:
            idx = int(part.strip()) - 1
            if 0 <= idx < len(pages):
                selected.append(pages[idx]["path"])
        except ValueError:
            continue
    return selected


def _answer(client, cfg, question: str, pages_content: list[dict]) -> str:
    context = "\n\n---\n\n".join(
        f"### [{p['name']}]\n\n{p['content'][:MAX_PAGE_CHARS]}"
        for p in pages_content
    )
    resp = client.chat.completions.create(
        model=cfg["model"],
        messages=[{
            "role": "user",
            "content": (
                f"다음 위키 페이지를 참고하여 질문에 답하세요.\n"
                f"위키에 없는 내용은 추측하지 말고 없다고 말하세요.\n"
                f"관련 페이지는 [[페이지명]] 형태로 인용하세요.\n\n"
                f"{context}\n\n질문: {question}\n\n답변:"
            ),
        }],
        temperature=cfg["temperature"],
        max_tokens=cfg["max_tokens"],
    )
    return resp.choices[0].message.content


def query(question: str, verbose: bool = True) -> tuple[str, list[str]]:
    client, cfg = get_client()
    wdir = wiki_dir()

    if not wdir.exists():
        return "위키가 아직 없습니다. 먼저 문서를 인제스트하세요.", []

    pages = _list_pages(wdir)
    if not pages:
        return "위키 페이지가 없습니다. 먼저 문서를 인제스트하세요.", []

    if verbose:
        print(f"🔍 위키 검색 중... (전체 {len(pages)}개 페이지)")

    relevant_paths = _select_pages(client, cfg, question, pages)

    if verbose:
        print(f"   선택된 페이지: {relevant_paths}")

    pages_content = []
    for path in relevant_paths:
        full = wdir / path
        if full.exists():
            pages_content.append({"name": full.stem, "path": path, "content": full.read_text("utf-8")})

    if not pages_content:
        return "관련 위키 페이지를 찾을 수 없습니다.", []

    answer = _answer(client, cfg, question, pages_content)
    return answer, relevant_paths


def main():
    parser = argparse.ArgumentParser(description="LLM-Wiki에 질문합니다.")
    parser.add_argument("question", help="질문 내용")
    parser.add_argument("--quiet", "-q", action="store_true")
    args = parser.parse_args()

    answer, refs = query(args.question, verbose=not args.quiet)
    print(f"\n{answer}")
    if refs and not args.quiet:
        print(f"\n참고: {', '.join(refs)}")


if __name__ == "__main__":
    main()

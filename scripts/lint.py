#!/usr/bin/env python3
"""Check LLM-Wiki health: broken links, orphaned pages.

Usage:
  python -m scripts.lint
  poetry run lint
"""

import re
import sys
import argparse
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from scripts.config import wiki_dir


def _wikilinks(content: str) -> set[str]:
    return set(re.findall(r"\[\[([^\]|#]+?)(?:\|[^\]]+)?\]\]", content))


def lint(verbose: bool = True) -> dict:
    wdir = wiki_dir()

    if not wdir.exists():
        if verbose:
            print("❌ 위키 디렉토리가 없습니다.")
        return {}

    all_pages: dict[str, Path] = {
        md.stem: md for md in wdir.rglob("*.md")
    }

    broken_links: list[dict] = []
    referenced: set[str] = set()

    for stem, path in all_pages.items():
        if stem in ("index", "log"):
            continue
        content = path.read_text("utf-8")
        for link in _wikilinks(content):
            referenced.add(link)
            if link not in all_pages:
                broken_links.append({"page": str(path.relative_to(wdir)), "link": link})

    orphaned = [
        str(p.relative_to(wdir))
        for stem, p in all_pages.items()
        if stem not in ("index", "log") and stem not in referenced
    ]

    result = {
        "total_pages": len(all_pages),
        "broken_links": broken_links,
        "orphaned_pages": orphaned,
    }

    if verbose:
        print(f"📊 위키 건강성 검사")
        print(f"   전체 페이지: {len(all_pages)}개")
        print(f"   깨진 링크: {len(broken_links)}개")
        for bl in broken_links:
            print(f"     ❌ {bl['page']} → [[{bl['link']}]]")
        print(f"   고아 페이지: {len(orphaned)}개")
        for op in orphaned:
            print(f"     ⚠️  {op}")
        if not broken_links and not orphaned:
            print("   ✅ 문제 없음!")

    return result


def main():
    parser = argparse.ArgumentParser(description="LLM-Wiki 건강성 검사.")
    parser.add_argument("--quiet", "-q", action="store_true")
    args = parser.parse_args()
    lint(verbose=not args.quiet)


if __name__ == "__main__":
    main()

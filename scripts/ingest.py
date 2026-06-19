#!/usr/bin/env python3
"""Ingest a document into the LLM-Wiki.

Usage:
  python -m scripts.ingest raw/문서.pdf
  poetry run ingest raw/문서.pdf
"""

import re
import sys
import argparse
from datetime import datetime
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from scripts.config import get_client, wiki_dir

CHUNK_CHARS = 10_000
MAX_CHUNKS = 10


def _extract_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        with pdfplumber.open(path) as pdf:
            return "\n".join(p.extract_text() or "" for p in pdf.pages)
    return path.read_text("utf-8")


def _chunks(text: str) -> list[str]:
    parts = []
    for i in range(0, len(text), CHUNK_CHARS):
        chunk = text[i : i + CHUNK_CHARS].strip()
        if chunk:
            parts.append(chunk)
    return parts[:MAX_CHUNKS]


def _slugify(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1F]', "", name).strip()[:80]


def _process_chunks(client, cfg, chunks: list[str], source_name: str, verbose: bool) -> dict:
    summaries, concepts, entities = [], set(), {}

    for i, chunk in enumerate(chunks):
        if verbose:
            print(f"   청크 {i + 1}/{len(chunks)} 분석 중...")
        resp = client.chat.completions.create(
            model=cfg["model"],
            messages=[{
                "role": "user",
                "content": (
                    f"다음은 '{source_name}'의 일부 텍스트입니다.\n\n"
                    f"{chunk}\n\n"
                    f"다음 형식으로만 답하세요:\n\n"
                    f"[요약]\n이 부분의 핵심 내용 2-3문장\n\n"
                    f"[핵심개념]\n개념1\n개념2\n(최대 7개)\n\n"
                    f"[주요엔티티]\n이름|타입\n이름|타입\n"
                    f"(타입: 기관/법령/제도/지표 중 하나, 최대 7개)"
                ),
            }],
            temperature=0,
            max_tokens=600,
        )
        text = resp.choices[0].message.content

        if "[요약]" in text:
            raw = text.split("[요약]")[1].split("[핵심개념]")[0].strip()
            if raw:
                summaries.append(raw)

        if "[핵심개념]" in text:
            raw = text.split("[핵심개념]")[1].split("[주요엔티티]")[0]
            for line in raw.splitlines():
                c = line.strip().lstrip("•-· ").strip()
                if c and len(c) < 40:
                    concepts.add(c)

        if "[주요엔티티]" in text:
            raw = text.split("[주요엔티티]")[1].strip()
            for line in raw.splitlines():
                line = line.strip().lstrip("•-· ").strip()
                if "|" in line:
                    name, etype = line.split("|", 1)
                    name, etype = name.strip(), etype.strip()
                    if name and len(name) < 40:
                        entities.setdefault(name, etype)

    return {
        "summaries": summaries,
        "concepts": sorted(concepts)[:15],
        "entities": dict(list(entities.items())[:15]),
    }


def _source_page(client, cfg, source_name: str, info: dict) -> str:
    concepts_md = "\n".join(f"- [[{c}]]" for c in info["concepts"])
    entities_md = "\n".join(f"- [[{n}]] ({t})" for n, t in info["entities"].items())
    summaries_md = "\n\n".join(info["summaries"])
    today = datetime.now().strftime("%Y-%m-%d")

    resp = client.chat.completions.create(
        model=cfg["model"],
        messages=[{
            "role": "user",
            "content": (
                f"다음 정보를 바탕으로 '{source_name}' 소스 페이지를 한국어 마크다운으로 작성하세요.\n\n"
                f"요약:\n{summaries_md}\n\n핵심 개념:\n{concepts_md}\n\n주요 엔티티:\n{entities_md}\n\n"
                f"반드시 다음 형식을 사용하세요:\n\n"
                f"---\ntype: source\ntitle: {source_name}\ndate_ingested: {today}\ntags: []\n---\n\n"
                f"# {source_name}\n\n## 개요\n\n## 핵심 개념\n\n## 주요 기관 및 제도\n\n## 주요 내용\n\n## 관련 문서"
            ),
        }],
        temperature=cfg["temperature"],
        max_tokens=cfg["max_tokens"],
    )
    return resp.choices[0].message.content


def _concept_page(client, cfg, name: str, source_name: str) -> str:
    resp = client.chat.completions.create(
        model=cfg["model"],
        messages=[{
            "role": "user",
            "content": (
                f"'{name}' 개념에 대한 위키 페이지를 한국어 마크다운으로 작성하세요. 출처: [[{source_name}]]\n\n"
                f"---\ntype: concept\ntitle: {name}\nsources: [[{source_name}]]\ntags: []\n---\n\n"
                f"# {name}\n\n## 정의\n\n## 상세 설명\n\n## 관련 개념\n\n## 출처\n- [[{source_name}]]"
            ),
        }],
        temperature=cfg["temperature"],
        max_tokens=800,
    )
    return resp.choices[0].message.content


def _entity_page(client, cfg, name: str, etype: str, source_name: str) -> str:
    resp = client.chat.completions.create(
        model=cfg["model"],
        messages=[{
            "role": "user",
            "content": (
                f"'{name}'({etype})에 대한 위키 페이지를 한국어 마크다운으로 작성하세요. 출처: [[{source_name}]]\n\n"
                f"---\ntype: entity\nentity_type: {etype}\ntitle: {name}\nsources: [[{source_name}]]\ntags: []\n---\n\n"
                f"# {name}\n\n## 개요\n\n## 역할 및 기능\n\n## 관련 법규\n\n## 출처\n- [[{source_name}]]"
            ),
        }],
        temperature=cfg["temperature"],
        max_tokens=600,
    )
    return resp.choices[0].message.content


def _update_index(wdir: Path, source_name: str, new_pages: list[dict]):
    index_path = wdir / "index.md"
    today = datetime.now().strftime("%Y-%m-%d")
    entry = f"\n\n## {source_name} ({today})\n" + "\n".join(
        f"- [[{p['name']}]] — {p['type']}" for p in new_pages
    )
    if index_path.exists():
        index_path.write_text(index_path.read_text("utf-8") + entry, "utf-8")
    else:
        index_path.write_text(f"# LLM-Wiki 인덱스\n{entry}", "utf-8")


def _append_log(wdir: Path, source_name: str, n: int):
    log_path = wdir / "log.md"
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"\n## [{now}] INGEST: {source_name}\n총 {n}개 페이지 생성\n"
    if not log_path.exists():
        log_path.write_text("# LLM-Wiki 변경 이력\n", "utf-8")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(entry)


def ingest(file_path: Path, verbose: bool = True) -> list[dict]:
    client, cfg = get_client()
    wdir = wiki_dir()
    source_name = file_path.stem

    if verbose:
        print(f"📄 처리 중: {file_path.name}")

    text = _extract_text(file_path)
    chunks = _chunks(text)

    if verbose:
        print(f"   텍스트: {len(text):,}자 → {len(chunks)}개 청크")

    info = _process_chunks(client, cfg, chunks, source_name, verbose)
    new_pages: list[dict] = []

    # Source page
    src_dir = wdir / "sources"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / f"{_slugify(source_name)}.md").write_text(
        _source_page(client, cfg, source_name, info), "utf-8"
    )
    new_pages.append({"name": source_name, "type": "source"})
    if verbose:
        print("   ✅ 소스 페이지")

    # Concept pages
    con_dir = wdir / "concepts"
    con_dir.mkdir(exist_ok=True)
    for concept in info["concepts"]:
        p = con_dir / f"{_slugify(concept)}.md"
        if not p.exists():
            p.write_text(_concept_page(client, cfg, concept, source_name), "utf-8")
            new_pages.append({"name": concept, "type": "concept"})
            if verbose:
                print(f"   ✅ 개념: {concept}")

    # Entity pages
    ent_dir = wdir / "entities"
    ent_dir.mkdir(exist_ok=True)
    for name, etype in info["entities"].items():
        p = ent_dir / f"{_slugify(name)}.md"
        if not p.exists():
            p.write_text(_entity_page(client, cfg, name, etype, source_name), "utf-8")
            new_pages.append({"name": name, "type": "entity"})
            if verbose:
                print(f"   ✅ 엔티티: {name}")

    _update_index(wdir, source_name, new_pages)
    _append_log(wdir, source_name, len(new_pages))

    if verbose:
        print(f"\n✅ 완료: {len(new_pages)}개 페이지 생성")

    return new_pages


def main():
    parser = argparse.ArgumentParser(description="문서를 LLM-Wiki로 인제스트합니다.")
    parser.add_argument("file", help="인제스트할 파일 경로 (PDF, TXT)")
    parser.add_argument("--quiet", "-q", action="store_true")
    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"❌ 파일 없음: {path}")
        sys.exit(1)

    ingest(path, verbose=not args.quiet)


if __name__ == "__main__":
    main()

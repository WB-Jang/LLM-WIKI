#!/usr/bin/env python3
"""Convert a PDF (or text) document into a knowledge graph.

Usage:
  python -m scripts.graphify raw/문서.pdf
  poetry run graphify raw/문서.pdf
  python -m scripts.graphify raw/문서.pdf --output graph.json
"""

import re
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path

import networkx as nx

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from scripts.config import get_client, wiki_dir
from scripts.ingest import _extract_text, _chunks, _slugify

ENTITY_TYPES = {"기관", "법령", "제도", "지표", "개념", "인물", "장소"}


def _extract_triplets(client, cfg, chunk: str, source_name: str, verbose: bool) -> list[dict]:
    resp = client.chat.completions.create(
        model=cfg["model"],
        messages=[{
            "role": "user",
            "content": (
                f"다음은 '{source_name}'의 텍스트입니다.\n\n"
                f"{chunk}\n\n"
                f"텍스트에서 엔티티 간의 관계를 추출하세요.\n\n"
                f"반드시 다음 형식으로만 답하세요:\n\n"
                f"[엔티티]\n"
                f"이름|타입\n"
                f"(타입: 기관/법령/제도/지표/개념/인물/장소 중 하나, 최대 15개)\n\n"
                f"[관계]\n"
                f"주체|관계|대상\n"
                f"(예: 금융위원회|감독|증권사, 최대 20개)\n\n"
                f"관계는 동사 또는 짧은 동사구로 표현하세요."
            ),
        }],
        temperature=0,
        max_tokens=800,
    )
    text = resp.choices[0].message.content

    entities: dict[str, str] = {}
    if "[엔티티]" in text:
        raw = text.split("[엔티티]")[1].split("[관계]")[0]
        for line in raw.splitlines():
            line = line.strip().lstrip("•-· ").strip()
            if "|" in line:
                name, etype = line.split("|", 1)
                name, etype = name.strip(), etype.strip()
                if name and len(name) < 40:
                    entities[name] = etype if etype in ENTITY_TYPES else "개념"

    triplets: list[dict] = []
    if "[관계]" in text:
        raw = text.split("[관계]")[1].strip()
        for line in raw.splitlines():
            line = line.strip().lstrip("•-· ").strip()
            parts = line.split("|")
            if len(parts) == 3:
                subj, rel, obj = [p.strip() for p in parts]
                if subj and rel and obj and len(subj) < 40 and len(obj) < 40:
                    triplets.append({
                        "source": subj,
                        "relation": rel,
                        "target": obj,
                        "source_type": entities.get(subj, "개념"),
                        "target_type": entities.get(obj, "개념"),
                    })

    return triplets


def _build_graph(all_triplets: list[dict]) -> nx.DiGraph:
    G = nx.DiGraph()
    for t in all_triplets:
        if not G.has_node(t["source"]):
            G.add_node(t["source"], type=t["source_type"])
        if not G.has_node(t["target"]):
            G.add_node(t["target"], type=t["target_type"])
        if G.has_edge(t["source"], t["target"]):
            # Accumulate multiple relations between same pair
            existing = G[t["source"]][t["target"]]["relation"]
            if t["relation"] not in existing:
                G[t["source"]][t["target"]]["relation"] = existing + ", " + t["relation"]
        else:
            G.add_edge(t["source"], t["target"], relation=t["relation"])
    return G


def _to_json(G: nx.DiGraph, source_name: str) -> dict:
    return {
        "meta": {
            "source": source_name,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "total_nodes": G.number_of_nodes(),
            "total_edges": G.number_of_edges(),
        },
        "nodes": [
            {"id": n, "type": G.nodes[n].get("type", "개념")}
            for n in G.nodes
        ],
        "edges": [
            {"source": u, "relation": d["relation"], "target": v}
            for u, v, d in G.edges(data=True)
        ],
    }


def graphify(file_path: Path, output: Path | None = None, verbose: bool = True) -> dict:
    client, cfg = get_client()
    source_name = file_path.stem

    if verbose:
        print(f"📄 처리 중: {file_path.name}")

    text = _extract_text(file_path)
    chunks = _chunks(text)

    if verbose:
        print(f"   텍스트: {len(text):,}자 → {len(chunks)}개 청크")

    all_triplets: list[dict] = []
    for i, chunk in enumerate(chunks):
        if verbose:
            print(f"   청크 {i + 1}/{len(chunks)} 관계 추출 중...")
        triplets = _extract_triplets(client, cfg, chunk, source_name, verbose)
        all_triplets.extend(triplets)
        if verbose:
            print(f"   → {len(triplets)}개 관계 발견")

    G = _build_graph(all_triplets)
    result = _to_json(G, source_name)

    if output is None:
        syn_dir = wiki_dir() / "synthesis"
        syn_dir.mkdir(parents=True, exist_ok=True)
        output = syn_dir / f"{_slugify(source_name)}.graph.json"

    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), "utf-8")

    if verbose:
        print(f"\n✅ 완료")
        print(f"   노드(엔티티): {result['meta']['total_nodes']}개")
        print(f"   엣지(관계):   {result['meta']['total_edges']}개")
        print(f"   저장 위치:    {output}")

    return result


def main():
    parser = argparse.ArgumentParser(description="PDF/텍스트를 지식 그래프로 변환합니다.")
    parser.add_argument("file", help="변환할 파일 경로 (PDF, TXT)")
    parser.add_argument("--output", "-o", help="출력 JSON 경로 (기본: wiki/synthesis/<파일명>.graph.json)")
    parser.add_argument("--quiet", "-q", action="store_true")
    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"❌ 파일 없음: {path}")
        sys.exit(1)

    out = Path(args.output) if args.output else None
    graphify(path, output=out, verbose=not args.quiet)


if __name__ == "__main__":
    main()

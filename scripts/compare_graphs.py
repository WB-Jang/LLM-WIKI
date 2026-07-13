#!/usr/bin/env python3
"""Compare two knowledge graphs on intrinsic quality metrics.

Each graph is evaluated independently — no graph is treated as ground truth.

Usage:
  python -m scripts.compare_graphs \\
    --ref-triplets path/to/triplets.csv \\
    --our-graph wiki/synthesis/<name>.graph.json \\
    [--law 금융실명법]
"""

import csv
import json
import math
import argparse
import sys
from pathlib import Path

import networkx as nx


# ── 데이터 로딩 ──────────────────────────────────────────────────────────────

def _load_ref_graph(triplets_csv: Path, law_filter: str | None) -> nx.DiGraph:
    G = nx.DiGraph()
    with open(triplets_csv, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if law_filter and row.get("law_nm", "") != law_filter:
                continue
            s, r, o = row["subject"].strip(), row["relation"].strip(), row["object"].strip()
            if not s or not r or not o:
                continue
            if not G.has_node(s):
                G.add_node(s, type=row.get("relation_category", ""))
            if not G.has_node(o):
                G.add_node(o, type=row.get("relation_category", ""))
            if G.has_edge(s, o):
                prev = G[s][o]["relation"]
                if r not in prev:
                    G[s][o]["relation"] = prev + ", " + r
            else:
                G.add_edge(s, o, relation=r)
    return G


def _load_our_graph(json_path: Path) -> nx.DiGraph:
    data = json.loads(json_path.read_text("utf-8"))
    G = nx.DiGraph()
    for n in data.get("nodes", []):
        G.add_node(n["id"], type=n.get("type", ""))
    for e in data.get("edges", []):
        s, o, r = e["source"], e["target"], e["relation"]
        if G.has_edge(s, o):
            prev = G[s][o]["relation"]
            if r not in prev:
                G[s][o]["relation"] = prev + ", " + r
        else:
            G.add_edge(s, o, relation=r)
    return G, data.get("meta", {})


# ── 지표 계산 ─────────────────────────────────────────────────────────────────

def _structural_integrity(G: nx.DiGraph) -> dict:
    n = G.number_of_nodes()
    if n == 0:
        return {}

    isolated = len(list(nx.isolates(G)))
    wcc = list(nx.weakly_connected_components(G))
    lcc_size = max(len(c) for c in wcc) if wcc else 0

    in_degrees = dict(G.in_degree())
    out_degrees = dict(G.out_degree())
    sink_nodes = sum(1 for v in G.nodes if out_degrees[v] == 0 and in_degrees[v] > 0)
    source_nodes = sum(1 for v in G.nodes if in_degrees[v] == 0 and out_degrees[v] > 0)

    return {
        "isolated_node_ratio": round(isolated / n, 3),
        "weakly_connected_components": len(wcc),
        "largest_component_ratio": round(lcc_size / n, 3),
        "sink_node_ratio": round(sink_nodes / n, 3),
        "source_node_ratio": round(source_nodes / n, 3),
    }


def _connectivity(G: nx.DiGraph) -> dict:
    n, e = G.number_of_nodes(), G.number_of_edges()
    if n < 2:
        return {}

    degrees = [d for _, d in G.degree()]
    avg_degree = round(sum(degrees) / n, 3)
    hub_threshold = avg_degree * 2
    hub_ratio = round(sum(1 for d in degrees if d >= hub_threshold) / n, 3)

    return {
        "density": round(nx.density(G), 5),
        "avg_degree": avg_degree,
        "hub_ratio": hub_ratio,
        "reciprocity": round(nx.reciprocity(G), 3),
        "edge_node_ratio": round(e / n, 3),
    }


def _relation_quality(G: nx.DiGraph) -> dict:
    relations = [d["relation"] for _, _, d in G.edges(data=True)]
    if not relations:
        return {}

    # 단일 relation만 집계 (복수 관계는 첫 번째만)
    primary = [r.split(",")[0].strip() for r in relations]

    freq: dict[str, int] = {}
    for r in primary:
        freq[r] = freq.get(r, 0) + 1

    total = len(primary)
    entropy = -sum((c / total) * math.log2(c / total) for c in freq.values() if c > 0)
    max_entropy = math.log2(len(freq)) if len(freq) > 1 else 1
    normalized_entropy = round(entropy / max_entropy, 3) if max_entropy else 0

    avg_label_len = round(sum(len(r) for r in freq) / len(freq), 2)

    # 노드당 고유 관계 수
    node_rels: dict[str, set] = {}
    for u, _, d in G.edges(data=True):
        node_rels.setdefault(u, set()).add(d["relation"].split(",")[0].strip())
    avg_unique_rels = round(sum(len(v) for v in node_rels.values()) / len(node_rels), 3) if node_rels else 0

    return {
        "unique_relations": len(freq),
        "relation_entropy": round(entropy, 3),
        "normalized_entropy": normalized_entropy,
        "avg_relation_label_len": avg_label_len,
        "avg_unique_rels_per_node": avg_unique_rels,
        "top_relations": dict(sorted(freq.items(), key=lambda x: -x[1])[:10]),
    }


def _graph_efficiency(G: nx.DiGraph) -> dict:
    # 최대 약연결 컴포넌트(LCC)에서만 계산 (전체 그래프에 적용 시 매우 느림)
    wcc = list(nx.weakly_connected_components(G))
    if not wcc:
        return {}
    lcc_nodes = max(wcc, key=len)
    lcc = G.subgraph(lcc_nodes).copy()
    lcc_undirected = lcc.to_undirected()

    result = {
        "clustering_coefficient": round(nx.average_clustering(lcc_undirected), 3),
    }

    # 500노드 이하일 때만 평균 최단 경로/지름 계산 (비용 큼)
    if len(lcc_nodes) <= 500 and nx.is_connected(lcc_undirected):
        try:
            result["avg_shortest_path"] = round(nx.average_shortest_path_length(lcc_undirected), 3)
            result["diameter"] = nx.diameter(lcc_undirected)
        except Exception:
            pass

    return result


def _extraction_efficiency(G: nx.DiGraph) -> dict:
    n, e = G.number_of_nodes(), G.number_of_edges()
    if n == 0:
        return {}

    # 노드 재사용률: subject이면서 동시에 object인 노드
    subjects = {u for u, _ in G.edges()}
    objects = {v for _, v in G.edges()}
    reused = subjects & objects
    reuse_ratio = round(len(reused) / n, 3) if n else 0

    return {
        "node_reuse_ratio": reuse_ratio,
    }


def _analyze(G: nx.DiGraph) -> dict:
    return {
        "basic": {
            "nodes": G.number_of_nodes(),
            "edges": G.number_of_edges(),
        },
        "structural_integrity": _structural_integrity(G),
        "connectivity": _connectivity(G),
        "relation_quality": _relation_quality(G),
        "graph_efficiency": _graph_efficiency(G),
        "extraction_efficiency": _extraction_efficiency(G),
    }


# ── 출력 ─────────────────────────────────────────────────────────────────────

def _fmt(v) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.3f}"
    return str(v)


def _print_report(ref_result: dict, our_result: dict, ref_label: str, our_label: str):
    sections = [
        ("기본 통계", "basic", [
            ("노드 수", "nodes"),
            ("엣지 수", "edges"),
        ]),
        ("구조적 완결성", "structural_integrity", [
            ("고립 노드 비율 ↓", "isolated_node_ratio"),
            ("약연결 컴포넌트 수 ↓", "weakly_connected_components"),
            ("최대 컴포넌트 비율 ↑", "largest_component_ratio"),
            ("싱크 노드 비율 ↓", "sink_node_ratio"),
            ("소스 노드 비율 ↓", "source_node_ratio"),
        ]),
        ("연결 밀도", "connectivity", [
            ("그래프 밀도 ↑", "density"),
            ("평균 차수 ↑", "avg_degree"),
            ("허브 노드 비율", "hub_ratio"),
            ("상호 엣지 비율", "reciprocity"),
            ("엣지/노드 비율 ↑", "edge_node_ratio"),
        ]),
        ("관계 정교함", "relation_quality", [
            ("고유 관계 수 ↑", "unique_relations"),
            ("관계 엔트로피 ↑", "relation_entropy"),
            ("정규화 엔트로피 ↑", "normalized_entropy"),
            ("관계 레이블 평균 길이 ↑", "avg_relation_label_len"),
            ("노드당 고유 관계 수 ↑", "avg_unique_rels_per_node"),
        ]),
        ("그래프 효율성", "graph_efficiency", [
            ("클러스터링 계수 ↑", "clustering_coefficient"),
            ("평균 최단 경로 ↓", "avg_shortest_path"),
            ("지름 ↓", "diameter"),
        ]),
        ("추출 효율", "extraction_efficiency", [
            ("노드 재사용률 ↑", "node_reuse_ratio"),
        ]),
    ]

    W = 26
    print("\n" + "=" * 70)
    print("  지식 그래프 내재적 품질 비교 리포트")
    print("=" * 70)
    print(f"  {'지표':<{W}}  {'참조 그래프':>14}  {'우리 그래프':>14}")
    print("-" * 70)

    for section_name, section_key, metrics in sections:
        print(f"\n  [{section_name}]")
        ref_sec = ref_result.get(section_key, {})
        our_sec = our_result.get(section_key, {})
        for label, key in metrics:
            rv = _fmt(ref_sec.get(key))
            ov = _fmt(our_sec.get(key))
            print(f"  {label:<{W}}  {rv:>14}  {ov:>14}")

    # 관계 분포
    print("\n  [참조 그래프 상위 관계]")
    for r, c in list(ref_result.get("relation_quality", {}).get("top_relations", {}).items())[:8]:
        print(f"    {r:<30} {c:>4}개")

    print("\n  [우리 그래프 상위 관계]")
    for r, c in list(our_result.get("relation_quality", {}).get("top_relations", {}).items())[:8]:
        print(f"    {r:<30} {c:>4}개")

    print("\n" + "=" * 70)
    print("  ↑: 높을수록 좋음  ↓: 낮을수록 좋음")
    print("=" * 70)


# ── 진입점 ───────────────────────────────────────────────────────────────────

def compare(ref_triplets: Path, our_graph: Path, law_filter: str | None = None) -> dict:
    ref_G = _load_ref_graph(ref_triplets, law_filter)
    our_G, our_meta = _load_our_graph(our_graph)

    return {
        "ref": _analyze(ref_G),
        "ours": _analyze(our_G),
        "meta": {
            "ref_source": str(ref_triplets),
            "ref_law_filter": law_filter or "all",
            "our_source": our_meta.get("source", str(our_graph)),
            "our_date": our_meta.get("date", "-"),
        },
    }


def main():
    parser = argparse.ArgumentParser(description="두 지식 그래프의 내재적 품질을 비교합니다.")
    parser.add_argument("--ref-triplets", required=True, help="참조 triplets CSV 경로")
    parser.add_argument("--our-graph", required=True, help="graphify JSON 경로")
    parser.add_argument("--law", help="비교할 법령 이름 (예: 금융실명법)")
    parser.add_argument("--output", "-o", help="결과 JSON 저장 경로")
    args = parser.parse_args()

    ref_path = Path(args.ref_triplets)
    our_path = Path(args.our_graph)
    for p in [ref_path, our_path]:
        if not p.exists():
            print(f"❌ 파일 없음: {p}")
            sys.exit(1)

    result = compare(ref_path, our_path, law_filter=args.law)
    _print_report(
        result["ref"], result["ours"],
        ref_label=result["meta"]["ref_source"],
        our_label=result["meta"]["our_source"],
    )

    if args.output:
        out = Path(args.output)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), "utf-8")
        print(f"\n결과 저장: {out}")


if __name__ == "__main__":
    main()

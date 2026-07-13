#!/usr/bin/env python3
"""Compare two knowledge graphs: CSV-pipeline output vs graphify JSON output.

Usage:
  python -m scripts.compare_graphs \\
    --ref-triplets path/to/triplets.csv \\
    --our-graph wiki/synthesis/<name>.graph.json \\
    [--law 금융실명법]   # optional: filter reference by law name
"""

import csv
import json
import argparse
import sys
from pathlib import Path


def _load_ref_graph(triplets_csv: Path, law_filter: str | None) -> dict:
    """Load reference graph from triplets CSV."""
    nodes: dict[str, str] = {}  # name -> type
    edges: list[dict] = []

    with open(triplets_csv, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if law_filter and row.get("law_nm", "") != law_filter:
                continue
            subj = row["subject"].strip()
            obj = row["object"].strip()
            rel = row["relation"].strip()
            if not subj or not obj or not rel:
                continue
            # Use relation_category as rough type
            nodes.setdefault(subj, row.get("relation_category", ""))
            nodes.setdefault(obj, row.get("relation_category", ""))
            edges.append({
                "source": subj,
                "relation": rel,
                "target": obj,
                "article": row.get("article_number", ""),
                "confidence": _to_float(row.get("confidence", "")),
                "eval_score": _to_float(row.get("eval_score", "")),
            })

    return {"nodes": nodes, "edges": edges}


def _load_our_graph(json_path: Path) -> dict:
    """Load graphify JSON output."""
    data = json.loads(json_path.read_text("utf-8"))
    nodes = {n["id"]: n.get("type", "") for n in data.get("nodes", [])}
    edges = data.get("edges", [])
    return {"nodes": nodes, "edges": edges, "meta": data.get("meta", {})}


def _to_float(val: str) -> float | None:
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _edge_key(e: dict) -> tuple:
    return (e["source"], e["target"])


def _node_overlap(ref_nodes: dict, our_nodes: dict) -> dict:
    ref_set = set(ref_nodes)
    our_set = set(our_nodes)
    exact = ref_set & our_set
    # Partial: our node is substring of ref node or vice versa
    partial = set()
    for o in our_set - exact:
        for r in ref_set - exact:
            if o in r or r in o:
                partial.add(o)
                break
    return {
        "ref_total": len(ref_set),
        "our_total": len(our_set),
        "exact_overlap": len(exact),
        "partial_overlap": len(partial),
        "only_in_ref": sorted(ref_set - our_set - {r for r in ref_set if any(o in r or r in o for o in our_set)})[:20],
        "only_in_ours": sorted(our_set - exact)[:20],
        "overlap_examples": sorted(exact)[:20],
    }


def _edge_overlap(ref_edges: list, our_edges: list) -> dict:
    ref_pairs = {_edge_key(e) for e in ref_edges}
    our_pairs = {_edge_key(e) for e in our_edges}
    exact = ref_pairs & our_pairs

    # Partial: same source or same target
    partial = set()
    for o in our_pairs - exact:
        for r in ref_pairs - exact:
            if o[0] == r[0] or o[1] == r[1]:
                partial.add(o)
                break

    # Relation distribution in each graph
    def rel_dist(edges):
        d = {}
        for e in edges:
            d[e["relation"]] = d.get(e["relation"], 0) + 1
        return dict(sorted(d.items(), key=lambda x: -x[1])[:15])

    return {
        "ref_total": len(ref_edges),
        "our_total": len(our_edges),
        "exact_pair_overlap": len(exact),
        "partial_pair_overlap": len(partial),
        "ref_top_relations": rel_dist(ref_edges),
        "our_top_relations": rel_dist(our_edges),
        "overlap_pairs": [{"source": s, "target": t} for s, t in sorted(exact)[:10]],
    }


def _avg(vals):
    v = [x for x in vals if x is not None]
    return round(sum(v) / len(v), 3) if v else None


def compare(
    ref_triplets: Path,
    our_graph: Path,
    law_filter: str | None = None,
) -> dict:
    ref = _load_ref_graph(ref_triplets, law_filter)
    ours = _load_our_graph(our_graph)

    node_cmp = _node_overlap(ref["nodes"], ours["nodes"])
    edge_cmp = _edge_overlap(ref["edges"], ours["edges"])

    ref_conf_avg = _avg([e.get("confidence") for e in ref["edges"]])
    ref_eval_avg = _avg([e.get("eval_score") for e in ref["edges"]])

    recall = round(node_cmp["exact_overlap"] / node_cmp["ref_total"], 3) if node_cmp["ref_total"] else 0
    precision = round(node_cmp["exact_overlap"] / node_cmp["our_total"], 3) if node_cmp["our_total"] else 0
    f1 = round(2 * precision * recall / (precision + recall), 3) if (precision + recall) else 0

    return {
        "summary": {
            "node_recall": recall,
            "node_precision": precision,
            "node_f1": f1,
            "edge_pair_overlap_rate": round(
                edge_cmp["exact_pair_overlap"] / edge_cmp["ref_total"], 3
            ) if edge_cmp["ref_total"] else 0,
        },
        "ref_meta": {
            "law_filter": law_filter or "all",
            "avg_confidence": ref_conf_avg,
            "avg_eval_score": ref_eval_avg,
            "source": str(ref_triplets),
        },
        "our_meta": ours.get("meta", {}),
        "nodes": node_cmp,
        "edges": edge_cmp,
    }


def _print_report(result: dict):
    s = result["summary"]
    nc = result["nodes"]
    ec = result["edges"]
    rm = result["ref_meta"]
    om = result["our_meta"]

    print("\n" + "=" * 60)
    print("  지식 그래프 품질 비교 리포트")
    print("=" * 60)

    print(f"\n[참조 그래프]  {rm['source']}")
    print(f"  법령 필터:   {rm['law_filter']}")
    print(f"  평균 신뢰도: {rm['avg_confidence']}")
    print(f"  평균 평가점: {rm['avg_eval_score']}")

    print(f"\n[우리 그래프]  {om.get('source', '-')}")
    print(f"  생성일:      {om.get('date', '-')}")

    print("\n── 노드(엔티티) 비교 ──────────────────────────────")
    print(f"  참조 그래프:   {nc['ref_total']:>5}개")
    print(f"  우리 그래프:   {nc['our_total']:>5}개")
    print(f"  완전 일치:     {nc['exact_overlap']:>5}개")
    print(f"  부분 일치:     {nc['partial_overlap']:>5}개")
    print(f"  Precision:    {s['node_precision']:.1%}")
    print(f"  Recall:       {s['node_recall']:.1%}")
    print(f"  F1:           {s['node_f1']:.1%}")

    print("\n── 엣지(관계) 비교 ──────────────────────────────")
    print(f"  참조 그래프:   {ec['ref_total']:>5}개")
    print(f"  우리 그래프:   {ec['our_total']:>5}개")
    print(f"  동일 쌍 일치:  {ec['exact_pair_overlap']:>5}개")
    print(f"  쌍 일치율:    {s['edge_pair_overlap_rate']:.1%}")

    print("\n── 참조 그래프 상위 관계 ────────────────────────")
    for rel, cnt in list(ec["ref_top_relations"].items())[:8]:
        print(f"  {rel:<20} {cnt:>4}개")

    print("\n── 우리 그래프 상위 관계 ────────────────────────")
    for rel, cnt in list(ec["our_top_relations"].items())[:8]:
        print(f"  {rel:<20} {cnt:>4}개")

    if nc["overlap_examples"]:
        print(f"\n── 일치 노드 예시 ({len(nc['overlap_examples'])}개) ──────────────────")
        for n in nc["overlap_examples"][:10]:
            print(f"  ✓ {n}")

    if nc["only_in_ours"]:
        print(f"\n── 우리 그래프만 발견 ({len(nc['only_in_ours'])}개) ─────────────────")
        for n in nc["only_in_ours"][:10]:
            print(f"  + {n}")

    print("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(description="두 지식 그래프의 품질을 비교합니다.")
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
    _print_report(result)

    if args.output:
        out = Path(args.output)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), "utf-8")
        print(f"\n💾 결과 저장: {out}")


if __name__ == "__main__":
    main()

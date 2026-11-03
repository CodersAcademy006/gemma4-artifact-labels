"""One row per released graph: size, test share, edge types. Cheap index.

Run: python3 -I graph_meta.py [--demo]
"""
import json, os, sys, collections
from pathlib import Path

# Competition data lives here. Override with GEMMA4_DATA=/path/to/data
DATA = Path(os.environ.get("GEMMA4_DATA",
                           str(Path.home() / "gemma4-paper/data")))


D = DATA / "graphs"


def is_test(nid):
    first = nid.split(".", 1)[0]
    return first == "tests" or first.startswith("test_") or first.endswith("_test")


def row(fn, g):
    lib = {n["id"] for n in g["nodes"] if not is_test(n["id"])}
    tchars = sum(len(n.get("text") or "") for n in g["nodes"] if n["id"] not in lib)
    chars = sum(len(n.get("text") or "") for n in g["nodes"])
    kinds = collections.Counter()
    for e in g["edges"]:
        s, t = e["source"] in lib, e["target"] in lib
        kinds["lib_lib" if s and t else ("test_test" if not s and not t else "cross")] += 1
    return {
        "graph": fn[:-5] if fn.endswith(".json") else fn,
        "repo": fn.split("_")[0],
        "base_commit": fn.split("_", 1)[1].removesuffix(".json"),
        "nodes": len(g["nodes"]), "test_nodes": len(g["nodes"]) - len(lib),
        "edges": len(g["edges"]), "edge_types": sorted({e["type"] for e in g["edges"]}),
        "node_keys": sorted({k for n in g["nodes"] for k in n}),
        "edge_keys": sorted({k for e in g["edges"] for k in e}),
        "text_chars": chars, "test_text_chars": tchars,
        "lib_lib": kinds["lib_lib"], "cross": kinds["cross"], "test_test": kinds["test_test"],
    }


def demo():
    g = {"nodes": [{"id": "lib.f", "name": "f", "text": "abc"},
                   {"id": "tests.t", "name": "t", "text": "de"}],
         "edges": [{"source": "tests.t", "target": "lib.f", "type": "calls", "key": 0}]}
    r = row("rich_abc.json", g)
    assert r["repo"] == "rich" and r["base_commit"] == "abc", r
    assert r["nodes"] == 2 and r["test_nodes"] == 1
    assert r["text_chars"] == 5 and r["test_text_chars"] == 2
    assert r["cross"] == 1 and r["lib_lib"] == 0 and r["test_test"] == 0
    assert r["node_keys"] == ["id", "name", "text"]
    print("demo ok")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        demo(); raise SystemExit
    rows = [row(fn, json.load(open(D / fn))) for fn in sorted(os.listdir(D))]
    with open("graph_meta.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print("graphs %d  nodes %d  edges %d" % (len(rows), sum(r["nodes"] for r in rows),
                                             sum(r["edges"] for r in rows)))
    print("test nodes %d (%.1f%%)" % (sum(r["test_nodes"] for r in rows),
          100 * sum(r["test_nodes"] for r in rows) / sum(r["nodes"] for r in rows)))
    print("text chars %d, test text %.1f%%" % (sum(r["text_chars"] for r in rows),
          100 * sum(r["test_text_chars"] for r in rows) / sum(r["text_chars"] for r in rows)))
    e = sum(r["edges"] for r in rows)
    for k in ("lib_lib", "cross", "test_test"):
        print("  %-10s %7d  %5.1f%%" % (k, sum(r[k] for r in rows), 100 * sum(r[k] for r in rows) / e))
    print("distinct edge types:", sorted({t for r in rows for t in r["edge_types"]}))
    print("distinct node key sets:", sorted({tuple(r["node_keys"]) for r in rows}))
    print("distinct edge key sets:", sorted({tuple(r["edge_keys"]) for r in rows}))

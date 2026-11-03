"""Rewrite the released graphs with test node text removed.

A test node keeps its id, its name and every edge it participates in; only its
`text` goes. That is the whole transformation. It exists because test code is
most of the text in these graphs and none of the edit targets, while the test
edges are 44% of the topology and cost almost nothing to keep.

Run: python3 -I stub.py --demo        self-check, no writes
     python3 -I stub.py --count       report the budget, no writes
     python3 -I stub.py --out DIR     write the stubbed graphs
"""
import json, os, sys
from pathlib import Path

# Competition data lives here. Override with GEMMA4_DATA=/path/to/data
DATA = Path(os.environ.get("GEMMA4_DATA",
                           str(Path.home() / "gemma4-paper/data")))


D = DATA / "graphs"


def is_test(nid):
    first = nid.split(".", 1)[0]
    return first == "tests" or first.startswith("test_") or first.endswith("_test")


def stub(graph):
    """Same graph object, test node text emptied. Edges untouched."""
    for n in graph["nodes"]:
        if is_test(n["id"]):
            n["text"] = ""
    return graph


def size(graph):
    """Characters of the JSON payload that actually carries content."""
    return sum(len(n["id"]) + len(n["name"]) + len(n.get("text") or "")
               for n in graph["nodes"])


def demo():
    g = {"nodes": [{"id": "lib.f", "name": "f", "text": "def f(): pass"},
                   {"id": "tests.test_f", "name": "test_f", "text": "def test_f(): f()"}],
         "edges": [{"source": "tests.test_f", "target": "lib.f", "type": "calls", "key": 0}]}
    before, edges = size(g), len(g["edges"])
    s = stub(json.loads(json.dumps(g)))
    assert len(s["edges"]) == edges, "edges must survive"
    assert s["nodes"][0]["text"] == "def f(): pass", "library text must survive"
    assert s["nodes"][1]["text"] == "" and s["nodes"][1]["name"] == "test_f"
    assert size(s) == before - len("def test_f(): f()")
    assert is_test("tests.a") and is_test("test_x.y") and not is_test("fastapi.sse")
    print("demo ok")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        demo(); raise SystemExit
    out = None
    if "--out" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--out") + 1])
        out.mkdir(parents=True, exist_ok=True)
    full = stubbed = deleted = 0
    e_all = e_kept = 0
    for fn in sorted(os.listdir(D)):
        g = json.load(open(D / fn))
        full += size(g)
        lib = {n["id"] for n in g["nodes"] if not is_test(n["id"])}
        deleted += sum(len(n["id"]) + len(n["name"]) + len(n.get("text") or "")
                       for n in g["nodes"] if n["id"] in lib)
        e_all += len(g["edges"])
        e_kept += sum(1 for e in g["edges"]
                      if e["source"] in lib and e["target"] in lib)
        s = stub(g)
        stubbed += size(s)
        if out:
            json.dump(s, open(out / fn, "w"))
    print("A full graph       %13d chars  1.00x  edges 100.0%%" % full)
    print("B test text gone   %13d chars  %.2fx  edges 100.0%%" % (stubbed, full / stubbed))
    print("C test nodes gone  %13d chars  %.2fx  edges %5.1f%%"
          % (deleted, full / deleted, 100 * e_kept / e_all))
    print("cost of keeping the topology: %d chars = %.2f%% of A"
          % (stubbed - deleted, 100 * (stubbed - deleted) / full))
    if out:
        print("wrote %d graphs to %s" % (len(os.listdir(out)), out))

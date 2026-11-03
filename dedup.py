"""How many characters of node text are the same text twice?

Two sources of duplication in these graphs:
  exact   -- two nodes whose `text` is byte-identical (same helper in many files)
  nested  -- a node whose id is a dotted prefix of another AND whose text
             contains that other node's text (a class carrying its methods)

Run: python3 -I dedup.py [--demo]
"""
import json, os, sys, hashlib
from pathlib import Path

# Competition data lives here. Override with GEMMA4_DATA=/path/to/data
DATA = Path(os.environ.get("GEMMA4_DATA",
                           str(Path.home() / "gemma4-paper/data")))


GDIR = DATA / "graphs"


def scan(nodes):
    """nodes: [(id, text)] -> (total, unique, nested) character counts."""
    total = sum(len(t) for _, t in nodes)
    seen, unique = set(), 0
    for _, t in nodes:
        h = hashlib.blake2b(t.encode(), digest_size=16).digest()
        if h not in seen:
            seen.add(h); unique += len(t)
    byid = dict(nodes)
    nested = 0
    for nid, t in nodes:
        parent = nid.rsplit(".", 1)[0]
        while parent:
            pt = byid.get(parent)
            if pt is not None and t and t in pt:
                nested += len(t); break
            if "." not in parent: break
            parent = parent.rsplit(".", 1)[0]
    return total, unique, nested


def demo():
    nodes = [("m.C", "class C:\n    def f(self):\n        return 1\n"),
             ("m.C.f", "    def f(self):\n        return 1\n"),
             ("m.g", "def g(): pass"),
             ("m.h", "def g(): pass")]          # identical text to m.g
    total, unique, nested = scan(nodes)
    assert total == sum(len(t) for _, t in nodes), total
    assert unique == total - len("def g(): pass"), (unique, total)
    assert nested == len(nodes[1][1]), nested
    print("demo ok")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        demo(); raise SystemExit
    T = U = N = 0
    per = []
    for fn in sorted(os.listdir(GDIR)):
        g = json.load(open(os.path.join(GDIR, fn)))
        nodes = [(n["id"], n.get("text") or "") for n in g["nodes"]]
        t, u, n = scan(nodes)
        T += t; U += u; N += n
        per.append((fn.split("_")[0], t, u, n))
    print("total text chars   %13d" % T)
    print("unique text chars  %13d  (%.1f%% exact-duplicate)" % (U, 100 * (T - U) / T))
    print("nested in a parent %13d  (%.1f%% of all text)" % (N, 100 * N / T))
    agg = {}
    for repo, t, u, n in per:
        a = agg.setdefault(repo, [0, 0, 0])
        a[0] += t; a[1] += u; a[2] += n
    for repo, (t, u, n) in sorted(agg.items(), key=lambda x: -x[1][0]):
        print("  %-9s total %12d  dup %5.1f%%  nested %5.1f%%" %
              (repo, t, 100 * (t - u) / t, 100 * n / t))

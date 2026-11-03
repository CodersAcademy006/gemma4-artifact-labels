"""Can the problem statement retrieve the node that has to change?

Lexical retrieval only: no model, no GPU, no embeddings. Query = the task's
problem_statement. Documents = the `text` of every node in that task's graph.
Gold = the nodes that reach.py resolved the gold hunks to.

Variants:
  full  -- rank every node in the released graph
  lib   -- rank library nodes only (test nodes removed)
and a one-hop expansion over `calls` edges from the top text hit, with test
nodes allowed as intermediaries or not, which is the pruning question from the
companion audit.

Run: python3 -I retrieve.py [--demo]
"""
import json, os, re, sys, math, collections
from pathlib import Path

# Competition data lives here. Override with GEMMA4_DATA=/path/to/data
DATA = Path(os.environ.get("GEMMA4_DATA",
                           str(Path.home() / "gemma4-paper/data")))


D = DATA
TOK = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
KS = (1, 5, 10, 20, 50)


def is_test(nid):
    first = nid.split(".", 1)[0]
    return first == "tests" or first.startswith("test_") or first.endswith("_test")


def toks(s):
    """Identifiers, lowercased, plus their snake_case parts."""
    out = set()
    for w in TOK.findall(s):
        w = w.lower()
        out.add(w)
        if "_" in w:
            out.update(p for p in w.split("_") if len(p) > 2)
    return out


def rank(query, docs):
    """docs: {id: token set} -> ids sorted by IDF-weighted overlap, best first.

    Score = sum of idf over shared terms, divided by log(2+|doc|) so that a
    huge node cannot win by containing every term once.
    """
    n = len(docs) or 1
    df = collections.Counter(t for ts in docs.values() for t in ts)
    idf = {t: math.log(1 + n / (1 + df[t])) for t in query}
    scored = []
    for nid, ts in docs.items():
        hit = query & ts
        if hit:
            scored.append((sum(idf[t] for t in hit) / math.log(2 + len(ts)), nid))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [nid for _, nid in scored]


def recall_at(ranked, gold, ks=KS):
    return {k: bool(set(ranked[:k]) & gold) for k in ks}


def demo():
    docs = {"lib.a": toks("def validate_sse_field(name): pass"),
            "lib.b": toks("def unrelated_helper(x): return x"),
            "tests.t": toks("def test_validate_sse_field(): validate_sse_field('a')")}
    q = toks("validate sse field rejects null")
    r = rank(q, docs)
    assert r[0] in ("lib.a", "tests.t"), r
    assert recall_at(["x", "lib.a"], {"lib.a"})[1] is False
    assert recall_at(["x", "lib.a"], {"lib.a"})[5] is True
    assert is_test("tests.foo.bar") and is_test("test_x.y") and not is_test("fastapi.sse")
    print("demo ok")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        demo(); raise SystemExit

    short = {"fastapi/fastapi": "fastapi", "Textualize/rich": "rich",
             "psf/requests": "requests", "encode/httpx": "httpx"}
    tasks = {json.loads(l)["instance_id"]: json.loads(l) for l in open(DATA / "tasks.jsonl")}
    loc = {json.loads(l)["instance_id"]: json.loads(l) for l in open("reachability.jsonl")}

    agg = {v: collections.Counter() for v in ("full", "lib", "oracle", "post")}
    hop = collections.Counter()
    n_eval = 0
    cache_key = cache = None
    order = sorted(tasks, key=lambda i: (tasks[i]['repo'], tasks[i]['base_commit']))
    for iid in order:
        t = tasks[iid]
        # gold = LIBRARY nodes only. Two fastapi tasks resolve to test nodes
        # that embed the library's expected output verbatim; those are resolver
        # false positives, not edit targets, so they cannot count as gold.
        gold = {nid for h in loc[iid]["hunks"] for nid in h["nodes"] if not is_test(nid)}
        if not gold:
            continue
        key = "%s_%s.json" % (short[t["repo"]], t["base_commit"])
        if key != cache_key:
            g = json.load(open(D / "graphs" / key))
            cache = ({n["id"]: toks(n.get("text") or "") for n in g["nodes"]},
                     g["links"] if "links" in g else g["edges"])
            cache_key = key
        docs, links = cache
        q = toks(t["problem_statement"])
        n_eval += 1

        libdocs = {k: v for k, v in docs.items() if not is_test(k)}
        full = rank(q, docs)
        lib = rank(q, libdocs)
        # oracle query: the pre-patch lines the fix deleted. A perfect bug
        # report would describe this code; the statement usually does not.
        pre = toks("\n".join(l[1:] for l in t["patch"].split("\n")
                             if l.startswith("-") and not l.startswith("---")))
        orc = rank(pre, libdocs) if pre else []
        # non-circular variant: the lines the fix ADDED. The resolver never
        # looked at these, so overlap with node text is not built in.
        post = toks("\n".join(l[1:] for l in t["patch"].split("\n")
                              if l.startswith("+") and not l.startswith("+++")))
        pst = rank(post, libdocs) if post else []
        for name, ranked in (("full", full), ("lib", lib), ("oracle", orc), ("post", pst)):
            for k, ok in recall_at(ranked, gold).items():
                agg[name][k] += ok

        # one hop out of the best library text hit, over `calls` edges
        if lib:
            seed = lib[0]
            nbr_all, nbr_lib = set(), set()
            for e in links:
                s, tg = e["source"], e["target"]
                if s == seed: nbr_all.add(tg)
                elif tg == seed: nbr_all.add(s)
            nbr_lib = {x for x in nbr_all if not is_test(x)}
            # two hops, with and without test nodes as stepping stones
            two_with, two_without = set(nbr_all), set(nbr_lib)
            for e in links:
                s, tg = e["source"], e["target"]
                if s in nbr_all: two_with.add(tg)
                if tg in nbr_all: two_with.add(s)
                if s in nbr_lib: two_without.add(tg)
                if tg in nbr_lib: two_without.add(s)
            hop["top1_is_gold"] += seed in gold
            hop["1hop"] += bool(nbr_lib & gold)
            hop["2hop_via_tests"] += bool({x for x in two_with if not is_test(x)} & gold)
            hop["2hop_lib_only"] += bool(two_without & gold)

    print("tasks with >=1 resolvable gold node: %d of %d (ceiling %.1f%%)"
          % (n_eval, len(tasks), 100 * n_eval / len(tasks)))
    print("\nrecall@k over the %d evaluable tasks (share of all 129 in brackets)" % n_eval)
    print("  k    full graph   library only   pre-patch query   post-patch query")
    for k in KS:
        f, l, o, p = (agg[v][k] for v in ("full", "lib", "oracle", "post"))
        print("  %-4d %7.1f%%     %7.1f%%        %7.1f%%          %7.1f%%"
              % (k, 100 * f / n_eval, 100 * l / n_eval,
                 100 * o / n_eval, 100 * p / n_eval))
    print("\nexpansion from the top-1 library hit")
    for k in ("top1_is_gold", "1hop", "2hop_lib_only", "2hop_via_tests"):
        print("  %-16s %5.1f%%" % (k, 100 * hop[k] / n_eval))

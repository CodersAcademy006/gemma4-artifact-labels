"""Resolve each patch hunk to nodes in the provided code graph.

A hunk is 'reachable' if its pre-patch lines (context + deleted) appear in the
text of at least one graph node. Unreachable hunks are real fixes the provided
representation cannot point an agent at.

Hunks are bucketed by the file they touch, because the graph is a Python AST
call-graph of the library: non-Python files and test files are out of scope by
construction, so only the SOURCE bucket is a defect in the representation.
"""
import json, os, re, sys, collections
from pathlib import Path

# Competition data lives here. Override with GEMMA4_DATA=/path/to/data
DATA = Path(os.environ.get("GEMMA4_DATA",
                           str(Path.home() / "gemma4-paper/data")))


D = DATA
MIN_LEN = 20        # ignore trivially short lines like "    return"
MIN_PROBES = 2      # a hunk needs this many usable pre-patch lines to judge

def bucket(path):
    """source | test | nonpy -- which part of the repo this file is."""
    base = path.rsplit("/", 1)[-1]
    if not path.endswith(".py"):
        return "nonpy"
    if (path.startswith("tests/") or "/tests/" in path
            or base.startswith("test_") or base.endswith("_test.py")
            or base == "conftest.py"):
        return "test"
    return "source"

def split_patch(patch):
    """[(path, hunk_body), ...] -- keeps each hunk attached to its file.

    These patches carry no 'diff --git' line; files are delimited only by a
    '--- <old>' / '+++ <new>' header pair.
    """
    out = []
    parts = re.split(r"^--- (\S+)[^\n]*\n\+\+\+ (\S+)[^\n]*\n", patch, flags=re.M)
    for i in range(1, len(parts) - 2, 3):
        old, new, body = parts[i], parts[i + 1], parts[i + 2]
        path = new[2:] if new.startswith("b/") else new
        if path == "/dev/null":                       # deleted file
            path = old[2:] if old.startswith("a/") else old
        for h in re.split(r"^@@.*$", body, flags=re.M)[1:]:
            out.append((path, h))
    return out

def probes(hunk_body):
    """Lines present in the file BEFORE the patch: context (' ') and deleted ('-')."""
    out = []
    for l in hunk_body.split("\n"):
        if l[:1] in (" ", "-") and l[:3] != "---":
            s = l[1:].strip()
            if len(s) >= MIN_LEN:
                out.append(s)
    return out

def classify(task, nodes):
    res = []
    for path, h in split_patch(task["patch"]):
        p = probes(h)
        if len(p) < MIN_PROBES:
            res.append(("nolabel", path, []))   # too little pre-patch context to judge
            continue
        need = max(2, len(p) // 2)
        hit = [nid for nid, txt in nodes.items() if sum(x in txt for x in p) >= need]
        res.append(("reach" if hit else "unreach", path, hit))
    return res

def table(title, per_repo):
    print(f"\n=== {title} ===")
    print(f"{'repo':<10} {'hunks':>6} {'reach':>6} {'unreach':>8} {'nolabel':>8}  unreachable%")
    tot = collections.Counter()
    for repo, c in sorted(per_repo.items()):
        n = c["reach"] + c["unreach"]
        tot.update(c)
        pct = 100 * c["unreach"] / n if n else 0
        print(f"{repo:<10} {n+c['nolabel']:>6} {c['reach']:>6} {c['unreach']:>8} {c['nolabel']:>8}  {pct:>10.1f}%")
    n = tot["reach"] + tot["unreach"]
    pct = 100 * tot["unreach"] / n if n else 0
    print(f"{'ALL':<10} {n+tot['nolabel']:>6} {tot['reach']:>6} {tot['unreach']:>8} {tot['nolabel']:>8}  {pct:>10.1f}%")
    return tot

def main():
    tasks = [json.loads(l) for l in open(D / "tasks.jsonl")]
    by_bucket = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    rows = []
    for t in tasks:
        short = t["repo"].split("/")[-1]
        g = D / "graphs" / f"{short}_{t['base_commit']}.json"
        if not g.exists():
            by_bucket["source"][short]["nograph"] += 1
            continue
        graph = json.load(open(g))
        nodes = {n["id"]: (n.get("text") or "") for n in graph["nodes"]}
        r = classify(t, nodes)
        for kind, path, hit in r:
            by_bucket[bucket(path)][short][kind] += 1
        rows.append({
            "instance_id": t["instance_id"], "repo": t["repo"],
            "n_nodes": len(nodes), "n_edges": len(graph["edges"]),
            "hunks": [{"status": k, "path": p, "bucket": bucket(p), "nodes": h} for k, p, h in r],
        })

    for b in ("source", "test", "nonpy"):
        table(f"{b.upper()} files", by_bucket[b])

    # task-level, SOURCE hunks only: the number that matters for localization
    def bad(r, only=None):
        return [h for h in r["hunks"]
                if h["status"] == "unreach" and (only is None or h["bucket"] == only)]
    print(f"\ntasks with a graph: {len(rows)}")
    print(f"  >=1 unreachable SOURCE hunk: {sum(1 for r in rows if bad(r,'source'))}")
    print(f"  >=1 unreachable hunk of any kind: {sum(1 for r in rows if bad(r))}")
    src_only = [r for r in rows if any(h['bucket']=='source' for h in r['hunks'])]
    print(f"  tasks that touch any source file at all: {len(src_only)}")
    out = Path("reachability.jsonl")
    with open(out, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print("wrote", out)

def demo():
    """Self-check: probes() keeps pre-patch lines; split_patch keeps file paths; bucket() sorts them."""
    h = "\n context line that is definitely long enough\n-deleted line that is long enough too\n+added line that is long enough also\n"
    p = probes(h)
    assert any("context line" in x for x in p), p
    assert any("deleted line" in x for x in p), p
    assert not any("added line" in x for x in p), p
    pa = ("--- a/fastapi/x.py\n+++ b/fastapi/x.py\n@@ -1 +1 @@\n-a\n+b\n"
          "--- a/tests/test_y.py\n+++ b/tests/test_y.py\n@@ -2 +2 @@\n-c\n+d\n"
          "--- a/rich/gone.py\n+++ /dev/null\n@@ -3 +0,0 @@\n-e\n")
    s = split_patch(pa)
    assert [x[0] for x in s] == ["fastapi/x.py", "tests/test_y.py", "rich/gone.py"], s
    assert bucket("fastapi/x.py") == "source"
    assert bucket("tests/test_y.py") == "test"
    assert bucket("tests/utils.py") == "test"
    assert bucket("docs/index.md") == "nonpy"
    assert bucket("conftest.py") == "test"
    print("demo ok")

if __name__ == "__main__":
    demo() if "--demo" in sys.argv else main()

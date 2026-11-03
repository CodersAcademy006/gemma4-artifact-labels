"""Does the agent's working tree contain a test that fails?

The harness applies `test_patch` only AFTER grading starts, in a fresh
container. So whatever `test_patch` ADDS does not exist while the agent works.
This counts how much of each task's correctness spec is new code.

Run: python3 -I tests_sig.py [--demo]
"""
import json, os, re, sys, collections
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # -I drops cwd
from leak import split_patch

# Competition data lives here. Override with GEMMA4_DATA=/path/to/data
DATA = Path(os.environ.get("GEMMA4_DATA",
                           str(Path.home() / "gemma4-paper/data")))



def hunk_shape(hunk):
    """'add' if the hunk only inserts lines, else 'edit'."""
    for l in hunk.split("\n"):
        if l.startswith("-") and not l.startswith("---"):
            return "edit"
    return "add"


def new_test_funcs(patch):
    return {m.group(1) for m in re.finditer(r"^\+\s*(?:async )?def\s+(test\w*)",
                                            patch, flags=re.M)}


def removed_test_funcs(patch):
    return {m.group(1) for m in re.finditer(r"^-\s*(?:async )?def\s+(test\w*)",
                                            patch, flags=re.M)}


def created_files(patch):
    """Files this patch brings into existence: their first hunk header is -0,0."""
    out = []
    for m in re.finditer(r"^--- (\S+)[^\n]*\n\+\+\+ (\S+)[^\n]*\n@@ -0,0", patch, flags=re.M):
        new = m.group(2)
        out.append(new[2:] if new.startswith("b/") else new)
    return sorted(set(out))


def measure(task):
    hunks = split_patch(task["test_patch"])
    shapes = collections.Counter(hunk_shape(h) for _, h in hunks)
    files = sorted({p for p, _ in hunks})
    created = created_files(task["test_patch"])
    return {
        "instance_id": task["instance_id"],
        "repo": task["repo"],
        "test_files": len(files),
        "test_hunks": len(hunks),
        "add_only_hunks": shapes["add"],
        "edit_hunks": shapes["edit"],
        "pure_addition": shapes["edit"] == 0 and shapes["add"] > 0,
        "new_test_funcs": len(new_test_funcs(task["test_patch"])),
        "removed_test_funcs": len(removed_test_funcs(task["test_patch"])),
        # candidate FAIL_TO_PASS: test functions this task's spec introduces.
        # The released records carry no FAIL_TO_PASS field; this is derived.
        "new_test_names": sorted(new_test_funcs(task["test_patch"])),
        "removed_test_names": sorted(removed_test_funcs(task["test_patch"])),
        "test_paths": sorted({p for p, _ in hunks}),
        "created_test_paths": created,
        "test_added_lines": sum(1 for l in task["test_patch"].split("\n")
                                if l.startswith("+") and not l.startswith("+++")),
        "creates_test_file": bool(created),
    }


def demo():
    t = {"instance_id": "a", "repo": "r/r",
         "test_patch": "--- a/tests/test_x.py\n+++ b/tests/test_x.py\n@@ -1,2 +1,4 @@\n"
                       " import x\n+def test_new():\n+    assert x.f() == 1\n"}
    m = measure(t)
    assert m["pure_addition"] and m["add_only_hunks"] == 1 and m["edit_hunks"] == 0, m
    assert m["new_test_funcs"] == 1 and m["removed_test_funcs"] == 0, m
    t2 = {"instance_id": "b", "repo": "r/r",
          "test_patch": "--- a/tests/test_y.py\n+++ b/tests/test_y.py\n@@ -1,3 +1,3 @@\n"
                        "-    assert f() == 1\n+    assert f() == 2\n"}
    m2 = measure(t2)
    assert not m2["pure_addition"] and m2["edit_hunks"] == 1, m2
    assert created_files("--- a/tests/new.py\n+++ b/tests/new.py\n@@ -0,0 +1,2 @@\n+x\n") == ["tests/new.py"]
    assert created_files("--- a/tests/old.py\n+++ b/tests/old.py\n@@ -3,2 +3,3 @@\n+x\n") == []
    print("demo ok")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        demo(); raise SystemExit
    rows = [measure(json.loads(l)) for l in open(DATA / "tasks.jsonl")]
    with open("tests_sig.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    n = len(rows)
    print("tasks", n)
    for k, pred in (("pure_addition", bool), ("creates_test_file", bool),
                    ("removed_test_funcs", lambda v: v > 0)):
        c = sum(1 for r in rows if pred(r[k]))
        print("%-20s %d/%d = %.1f%%" % (k, c, n, 100 * c / n))
    print("new test funcs added: total %d, median %d, max %d" % (
        sum(r["new_test_funcs"] for r in rows),
        sorted(r["new_test_funcs"] for r in rows)[n // 2],
        max(r["new_test_funcs"] for r in rows)))
    print("tasks adding 0 new test funcs:",
          sum(1 for r in rows if r["new_test_funcs"] == 0))
    print("hunks: add-only %d, edit %d" % (sum(r["add_only_hunks"] for r in rows),
                                           sum(r["edit_hunks"] for r in rows)))
    print(collections.Counter((r["repo"], r["pure_addition"]) for r in rows))

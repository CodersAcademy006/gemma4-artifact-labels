"""Measure what the task 'problem_statement' already tells the agent.

These statements are the descriptions of the pull requests that FIXED the bugs,
not pre-fix issue reports, so they can name files, symbols and code lines that
the gold patch introduces. This script counts that.

Run: python3 -I leak.py          (measure, writes leak.jsonl)
     python3 -I leak.py --demo   (self-check)
"""
import json, os, re, sys, collections
from pathlib import Path

# Competition data lives here. Override with GEMMA4_DATA=/path/to/data
DATA = Path(os.environ.get("GEMMA4_DATA",
                           str(Path.home() / "gemma4-paper/data")))


MIN_LINE = 20   # ponytail: same probe floor as reach.py, keeps 'return' out


def split_patch(patch):
    """[(path, hunk_body), ...]. No 'diff --git' line in these patches."""
    out = []
    parts = re.split(r"^--- (\S+)[^\n]*\n\+\+\+ (\S+)[^\n]*\n", patch, flags=re.M)
    for i in range(1, len(parts) - 2, 3):
        old, new, body = parts[i], parts[i + 1], parts[i + 2]
        path = new[2:] if new.startswith("b/") else new
        if path == "/dev/null":
            path = old[2:] if old.startswith("a/") else old
        for h in re.split(r"^@@.*$", body, flags=re.M)[1:]:
            out.append((path, h))
    return out


def added_lines(hunk):
    return [l[1:].strip() for l in hunk.split("\n") if l.startswith("+")]


def new_symbols(patch):
    """Names of functions/classes the patch ADDS."""
    return {m.group(2) for m in re.finditer(r"^\+\s*(?:async )?(def|class)\s+(\w+)",
                                            patch, flags=re.M)}


def norm(s):
    """Collapse whitespace so markdown-wrapped code still matches."""
    return re.sub(r"\s+", " ", s)


def gitmoji(stmt):
    """Leading non-word run of the title, which is the PR's gitmoji if it has one."""
    m = re.match(r"^([^\w\s\[\(`#\"]+)", stmt.strip())
    return m.group(1).strip() if m else ""


ISSUE_REF = re.compile(r"(?:#\d+|github\.com/[\w.-]+/[\w.-]+/(?:issues|discussions|pull)/\d+)")
BACKTICK = re.compile(r"`([^`\n]{2,60})`")
IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")


def touched_idents(patch):
    """Identifiers appearing on any changed (+/-) line of the gold patch."""
    out = set()
    for l in patch.split("\n"):
        if l[:1] in "+-" and not l.startswith(("+++", "---")):
            out.update(IDENT.findall(l[1:]))
    return out


def measure(task):
    stmt = task["problem_statement"]
    nstmt = norm(stmt)
    hunks = split_patch(task["patch"])
    paths = sorted({p for p, _ in hunks})
    adds = [a for _, h in hunks for a in added_lines(h) if len(a) >= MIN_LINE]
    syms = new_symbols(task["patch"])

    return {
        "instance_id": task["instance_id"],
        "repo": task["repo"],
        "files": len(paths),
        "hunks": len(hunks),
        # new file = every hunk header of that file starts the file at line 0
        "pr_template": bool(re.search(r"##\s*Pull Request|GitHub Discussion", stmt)),
        "says_this_pr": bool(re.search(r"\bthis (pull request|pr)\b", stmt, re.I)),
        "gitmoji": gitmoji(stmt),
        # does the statement name a gold file?
        "names_path": any(p in stmt for p in paths),
        "names_basename": any(p.rsplit("/", 1)[-1] in stmt for p in paths),
        # does the statement contain a line of the gold diff verbatim?
        "leaks_code": sum(1 for a in adds if norm(a) in nstmt),
        "added_lines": len(adds),
        # does it name a symbol the patch defines?
        "names_new_symbol": sorted(s for s in syms if re.search(r"\b%s\b" % re.escape(s), stmt)),
        "new_symbols": sorted(syms),
        "stmt_chars": len(stmt),
        # external issue/PR pointers whose text is NOT in the dataset
        "issue_refs": sorted(set(ISSUE_REF.findall(stmt))),
        # identifiers the statement puts in backticks, and how many of those
        # actually appear on a changed line of the gold patch
        "backticked": sorted({b.strip() for b in BACKTICK.findall(stmt)}),
        "backticked_hit": sorted({b for b in {b.strip() for b in BACKTICK.findall(stmt)}
                                  if set(IDENT.findall(b)) & touched_idents(task["patch"])}),
        "added_total": sum(1 for l in task["patch"].split("\n")
                           if l.startswith("+") and not l.startswith("+++")),
    }


def demo():
    t = {"instance_id": "x_1", "repo": "r/r",
         "problem_statement": "## Pull Request\nThis PR adds `def handle_event` in "
                              "src/sse.py. Now we call\n```\nreturn validate_sse_field(name)\n```\n",
         "patch": "--- a/src/sse.py\n+++ b/src/sse.py\n@@ -1,2 +1,4 @@\n"
                  " ctx\n+def handle_event(self):\n+    return validate_sse_field(name)\n"}
    m = measure(t)
    assert m["files"] == 1 and m["hunks"] == 1, m
    assert m["pr_template"] and m["says_this_pr"], m
    assert m["names_path"] and m["names_basename"], m
    assert m["new_symbols"] == ["handle_event"], m
    assert m["names_new_symbol"] == ["handle_event"], m
    assert m["leaks_code"] == 1, m        # the return line, verbatim
    assert m["added_lines"] == 2, m       # both added lines clear MIN_LINE
    assert gitmoji("\u2728 Add thing") == "\u2728", gitmoji("\u2728 Add thing")
    assert gitmoji("perf: faster") == "", gitmoji("perf: faster")
    # deleted-file + /dev/null path handling
    assert measure({"instance_id": "y", "repo": "r/r", "patch": "--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-x = old_name()\n+x = new_name()\n",
                    "problem_statement": "rename `old_name` to `new_name`, see #12"}) ["backticked_hit"] == ["new_name", "old_name"], "backtick hit"
    assert measure({"instance_id": "y", "repo": "r/r", "patch": "--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-x\n+y\n",
                    "problem_statement": "see #12 and github.com/o/r/issues/7"})["issue_refs"] == ["#12", "github.com/o/r/issues/7"], "issue refs"
    h = split_patch("--- a/gone.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-x\n")
    assert h and h[0][0] == "gone.py", h
    print("demo ok")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        demo(); raise SystemExit
    rows = [measure(json.loads(l)) for l in open(DATA / "tasks.jsonl")]
    with open("leak.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    n = len(rows)
    def pct(k, pred=bool):
        c = sum(1 for r in rows if pred(r[k]))
        return "%d/%d = %.1f%%" % (c, n, 100 * c / n)
    print("tasks                 ", n)
    print("PR-template boilerplate", pct("pr_template"))
    print("says 'this PR'         ", pct("says_this_pr"))
    print("names a gold file path ", pct("names_path"))
    print("names a gold basename  ", pct("names_basename"))
    print("names a new symbol     ", pct("names_new_symbol", lambda v: len(v) > 0))
    print("leaks >=1 gold code line", pct("leaks_code", lambda v: v > 0))
    print("names a backticked gold ident", pct("backticked_hit", lambda v: len(v) > 0))
    print("has backticks at all   ", pct("backticked", lambda v: len(v) > 0))
    print("refs an absent issue/PR", pct("issue_refs", lambda v: len(v) > 0))
    print("gitmoji                ", collections.Counter(r["gitmoji"] for r in rows).most_common())
    import statistics as st
    for k in ("stmt_chars", "hunks", "files", "added_total"):
        v = sorted(r[k] for r in rows)
        print("%-12s median %7.1f  mean %8.1f  max %6d" % (k, st.median(v), st.mean(v), v[-1]))

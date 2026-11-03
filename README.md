# Gemma 4 Developer Agent: artifact labels and audit scripts

Four label files over the released development set, and the seven standard-library
Python scripts that produce them. 364 KB total. No dependencies, no GPU, no network.
Every script carries an assertion-based self-check: run it with `--demo`.

Point `D` at your copy of the competition data (`tasks.jsonl` and `graphs/`), then:

```
python3 -I graph_meta.py     # graph_meta.jsonl    127 rows, one per graph
python3 -I reach.py          # reachability.jsonl  129 rows, 695 gold hunks labelled
python3 -I leak.py           # task_inputs.jsonl   129 rows, what each prompt names
python3 -I tests_sig.py      # test_spec.jsonl     129 rows, candidate FAIL_TO_PASS
python3 -I retrieve.py       # the no-model retrieval baseline, 4 seconds
python3 -I stub.py --count    # the text budget under three pruning variants
python3 -I dedup.py          # duplicate node text (a negative result: 4.5%)
```

## graph_meta.jsonl (127 rows)

One row per graph file: node and edge counts, test-node counts, text characters, the
library/cross/test edge split, and the observed node and edge key sets. Reproduces
367,985 nodes, 452,588 edges, 60.7% test nodes, 59.3% test text, and the single
observed edge type `calls`.

## reachability.jsonl (129 rows, 695 hunks)

Each gold patch hunk, with the file it touches, a `source` / `test` / `nonpy` bucket,
a status, and the node ids it resolved to.

`reach` 420, `unreach` 197, `nolabel` 78. A hunk is `reach` when some node's `text`
contains at least half, floor two, of its pre-patch lines of 20 characters or more;
`nolabel` when it has fewer than two such lines. 197 of 617 labelled hunks, 31.9%,
resolve to no node in the graph that ships with their own task.

Known false positive: two fastapi tasks resolve to test nodes that embed the library's
expected output verbatim. Filter node ids whose first dotted component is `tests`, or
starts with `test_`, or ends with `_test`, as the scripts here do.

## task_inputs.jsonl (129 rows)

What the `problem_statement` contains, per task: whether it calls itself a pull request,
carries the repository's pull-request template, references an issue or discussion whose
text is absent, names a path or basename from its own gold patch, names a function or
class the patch defines, repeats a gold diff line verbatim, and its maintainer intent
glyph where one exists. Plus patch shape: files, hunks, added lines.

## test_spec.jsonl (129 rows)

The withheld specification, described from the diff: test paths touched, which the patch
creates, whether it modifies any existing test line, and **495 candidate FAIL_TO_PASS
names**, being every `def test...` the patch introduces.

This is a derived stand-in, not the official criterion, which the released records do
not contain. It is wrong in three known ways: it is empty for the 22 tasks that only
edit existing tests, it gives bare function names without parametrised `[param]`
suffixes, and it says nothing about `PASS_TO_PASS`. Usable for 107 of 129 tasks.

## stub.py

Rewrites the graphs with test node `text` emptied, keeping the id, the name and every
edge. 308,770,346 content characters become 148,090,225, a 2.09x reduction with 100% of
edges retained. Deleting the test nodes outright gives 2.55x and retains 55.9% of edges.
`--out DIR` writes the rewritten graphs; `--count` only reports.

## retrieve.py

IDF-weighted identifier overlap over node text, one index per task. Recall at 10 over
the 114 tasks with a library gold node: 31.6% on the released graph, 44.7% with test
nodes removed, 89.5% when the query is replaced by the gold patch's added lines.

## Reuse

Public domain as far as the competition rules allow. If a number here is wrong, the
script that produced it is 150 lines and has a `--demo`; please correct it rather than
cite it.

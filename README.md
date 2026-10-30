# Repo lifetime simulation

Can a model write code that survives a repository's future? We test this on real Python repos whose later history the model hasn't seen. Each repo is frozen at the model's knowledge cutoff (2026-06-01). An agent hardens that snapshot without seeing anything later. The repo's own later tests, run against the hardened code, then act as an automatic score.

A second thread grew out of this: **repomap**, a tool that traces a test suite once and then says, without running anything, which pieces of a repo and which tests a change will affect.

## Headline findings

1. **Future tests make a usable reward signal.** Running a repo's later test suite against its past code gives an automatic score for "future-proof" code. Precision is high: 84% of the agents' fixes are real bugs, and 56% of all fixes are real bugs that upstream still hasn't fixed. So the future-test score is a floor.
2. **Agents anticipate latent bugs, not features.** Across 8 repos with 3 blind runs each, agents fixed 26% of the failing future tests with 3 regressions in 24 runs. They fixed about a third of the bug tests and none of the 49 feature tests.
3. **Misses come in whole kinds of bugs.** Agents are strong on state and caching bugs (77% caught) and weak on output formatting, domain rules, empty inputs and performance. A prompt that tells them to search those kinds raised distinct future bugs caught from 15 to 21 of 60 on held-out repos, with 0 regressions.
4. **Hardening barely gets in the way of real history.** Replaying upstream's later commits onto agent-hardened code, 15% of run-commit pairs collide, about the same for both prompts.
5. **A traced map predicts change impact almost perfectly.** On werkzeug, choosing tests by changed function caught all 85 tests whose result changed across 54 real commits, while running 24% of the suite. Against 200 injected bugs, every bug was caught and 99.7% of broken tests were selected, at a median of 0.6% of the suite.

## Contents

### Research

- [`research/repo-evolution-training-data.md`](research/repo-evolution-training-data.md): survey of benchmarks (SWE-CI, SWE-Milestone, SWE-Chain, SWE-EVO), training datasets and synthetic repo-evolution work as of October 2026, and where the gaps are.

### Future-requirements pilot ([`pilot/`](pilot/README.md))

Run in this order, each building on the last:

| Step | What it asks | Write-up |
|---|---|---|
| Pilot | Can an agent anticipate tinydb's and click's later bug fixes? (tinydb: future failures 9 → 5, 4 of 8 real bugs caught) | [`pilot/README.md`](pilot/README.md), [`pilot/tinydb/`](pilot/tinydb/) |
| Scale-up | Same on 8 repos, 3 blind runs each, then bug vs feature labels and sandboxed reruns | [`pilot/scale-up/README.md`](pilot/scale-up/README.md) |
| Analysis | Which future bugs do agents miss, and how many of their fixes are real? | [`pilot/analysis/README.md`](pilot/analysis/README.md) |
| Prompt A/B | Does a prompt built from the miss analysis catch more, on 4 held-out repos? | [`pilot/ab-test/README.md`](pilot/ab-test/README.md) |
| Replay | Do agent patches make upstream's real later commits harder to land? | [`pilot/replay/README.md`](pilot/replay/README.md) |

Tools: `screen.py` finds repos and their failing future tests, `blind.py` runs and scores hardening agents, `label.py` labels target tests as bug or feature, `audit.py` checks agent transcripts for leaks of future data, and `replay.py` merges upstream history onto agent patches.

### repomap ([`repomap/`](repomap/README.md))

Traces the test suite once under Python's `sys.monitoring`, recording which lines each test runs, who calls whom, and the values every function saw. From that memory:

```
repomap.py record --package src/mypkg   # trace the suite once
repomap.py impact Range.range_for_length # or path.py:LINE, or no argument for your uncommitted diff
repomap.py refresh                       # re-trace only the tests a change touches
repomap.py serve                         # the map and impact in your browser at http://localhost:8765
```

- Lookups take under a second. A refresh takes 2 to 16 s, compared with 33 s for a full record on werkzeug.
- Accuracy is measured two ways: on werkzeug's real history (`impact.py`) and on 200 injected bugs (`mutbench.py`). Both are in the [repomap README](repomap/README.md).
- [`repomap/examples/`](repomap/examples/README.md) walks through six small edits to a toy shop package, comparing what repomap predicts with the tests that really broke ([Shopkit Impact Examples](https://claude.ai/artifact/5QMS2QWpJhtr9LEPttiyeG)).
- [Werkzeug Repo Map](https://claude.ai/artifact/RVd9ak5h1iP4Zhkck5CoPc) is a snapshot of the `serve` page. [Werkzeug Change Impact](https://claude.ai/artifact/9AEvdA1qQ2EcVkbdqfVmjq) shows predictions against each real commit. Both links are private until shared.

## Next steps

- **Reward signal.** Package the pilot as an RL environment. Reward = future tests fixed + verified regression tests that fail on the snapshot − conflicts with upstream history.
- **More data.** More runs and repos, including larger ones and other languages.
- **repomap for agents.** Give hardening agents repomap's value gaps (for example "this argument was never empty") and measure whether they catch more future bugs.
- **repomap as a benchmark.** Run `record` and `mutbench.py` on the other 11 pilot repos and publish the faults, so any test-impact tool can be scored on them.

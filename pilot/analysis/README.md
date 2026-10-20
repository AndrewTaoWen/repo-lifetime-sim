# What blind hardening misses, and how precise it is

Two follow-ups to `../scale-up/README.md`, both using the 8 repos and the snapshot at 2026-06-01.

## 1. What the agents miss

Every target test labelled *bug* (see `../scale-up/labels.json`) was grouped by the upstream commit that fixed it, which gives **116 distinct real bugs**. Each was given one kind by hand (`bug-kinds.json`), then checked against all 32 hardening runs: the 24 from round 1 plus the 8 sandboxed ones. Per-bug results are in `bug-catch.json`.

| Kind | Bugs | Caught by any run | Per-run catch rate |
|---|---|---|---|
| State consistency (caches, indices, internal structures drifting after a mutation or lifecycle step) | 13 | 10 (77%) | 71% |
| Parser strictness (accepts input the spec forbids) | 13 | 7 (54%) | 29% |
| Object model (descriptors, binding, introspection, dunder protocols) | 16 | 8 (50%) | 28% |
| Falsy / sentinel confusion (False, None, 0 treated as missing) | 5 | 2 (40%) | 25% |
| Argument validation (should reject bad arguments) | 10 | 3 (30%) | 22% |
| Output fidelity (serialized output loses formatting, order or escaping) | 29 | 10 (34%) | 21% |
| Domain semantics (needs SQL, URL, datetime-fold or float-range knowledge) | 15 | 3 (20%) | 18% |
| Degenerate input (empty, zero-size, one-item) | 7 | 1 (14%) | 14% |
| Repr robustness (hostile values in trace or display output) | 5 | 1 (20%) | 5% |
| Performance (quadratic or unbounded work) | 3 | 0 | 0% |
| **All** | **116** | **45 (39%)** | **27%** |

What this says:

- **Catching is close to all-or-nothing.** 71 bugs were caught by no run, and 18 by all four runs for their repo. Only 27 were caught by some runs and not others. A bug is either salient from the code, or no agent goes near it. More runs of the same prompt won't close much of the gap.
- **Agents are good at state bugs.** Stale caches, IDs reused after a mixed insert, cache keys missing a parameter, eviction miscounting: these are what "think adversarially about every public API" finds.
- **They are weak where the spec is outside the code.** That covers which TOML spellings are illegal, URL fragments, SQL keywords and datetime `fold`. The agent has to know the domain rule, and the code doesn't show it.
- **Output fidelity is the biggest miss by volume.** 19 of tomlkit's 29 rendering bugs were never caught. They are layout cases (comments, separators, dotted keys, empty arrays of tables) that only show up when a document is edited and written back.
- **Degenerate inputs are a surprise.** Empty and zero-size inputs are the classic edge case, yet 6 of 7 were missed, 5 of them in more-itertools. That library has dozens of functions, and each agent sampled only a few of them.
- **Performance looks like 0%, but that's partly the test.** Sandboxed agents did fix tomlkit's quadratic inline-table rendering and a quadratic grouping path in sqlparse, both of which upstream also fixed (see below). Upstream's performance tests use different inputs or cover a different slow path, so they still fail.

## 2. How precise the fixes are

A separate reviewer agent per repo went through every fix from the 8 sandboxed runs (`precision/*.json`). For each fix it:

- ran the agent's regression test against the snapshot code, to confirm it fails there;
- judged whether the old behaviour is a real bug;
- searched upstream history after the snapshot for a fix to the same bug.

| | Fixes | Share |
|---|---|---|
| Total distinct fixes | 134 | |
| Regression test fails on the snapshot (checked by running it) | 130 | 97% |
| **Real bug** | 113 | 84% |
| Debatable (defensible policy or behaviour change) | 17 | 13% |
| Not a bug (cosmetic, or no measurable effect) | 4 | 3% |
| Covered by a future test (already counted in the scores) | 30 | 22% |
| Same bug fixed upstream, but its test doesn't pass on the agent's code | 9 | 7% |
| **Real bug with no upstream fix yet** | 75 | 56% |
| Conflicts with what upstream later chose | 4 | 3% |

What this says:

- **Most claims are real.** About 84% of fixes are bugs a user would reasonably call wrong, and 97% come with a test that fails on the old code. Earlier we only knew that 3 to 4 of tinydb's roughly 20 claimed fixes matched the future. The rest are not noise.
- **Most real bugs haven't been reported yet.** 75 of 113 have no upstream fix four to five months later. For tomlkit, the reviewer confirmed 15 of them still fail on upstream HEAD. The future-test score only sees the bugs users happened to report, so it is a lower bound on usefulness.
- **The test-based score undercounts by about a quarter.** 9 more fixes address the same bug as an upstream commit but don't pass upstream's test. Usually the agent picked a different behaviour, or fixed one case and upstream fixed a wider one. Counting them takes confirmed future bugs from 30 to 39.
- **Conflicts are rare but instructive.** There were 4:
  - cachetools: the class-access fix broke `mock.create_autospec`. This is the one regression in the run.
  - more-itertools: `last()` on a non-iterable still returns the default, where upstream now raises.
  - pluggy: when a traced value's `repr` raises, the agent only rebalanced the trace indent and still lets the error out. Upstream renders the value instead.
  - tinydb: the agent copies search results on every call, a fix upstream explicitly rejected as too costly.

## Caveats

- Bug kinds, real-bug verdicts and upstream matching are model judgements. Each reviewer was a fresh agent seeing the future history, but it's the same model family as the hardening agents, so the verdicts may be generous to them. The mechanical part, the regression test failing on the snapshot, held for 130 of 134 fixes.
- Precision covers only the 8 sandboxed runs, one per repo. Round-1 runs weren't reviewed.
- "No upstream fix yet" means none was found in the local clone up to each repo's latest commit (mid-October 2026). Open issues weren't searched.

## Implications for the next step

- **As a reward signal, future tests alone are too sparse.** Only 22% of good fixes earn credit, and an agent that finds real unreported bugs looks no better than one that churns. A reward should also credit verified regression tests that fail on the snapshot, perhaps with a reviewer check, and penalize conflicts with future tests.
- **Prompting has room in the weak kinds.** Asking agents to check each function's empty and zero-size inputs, to round-trip edited documents, and to check parsers against the spec might lift the categories that are near zero today.

## Files

- `bug-kinds.json`: the kind assigned to each upstream bug commit, with definitions.
- `bug-catch.json`: per-bug kind and how many runs caught it.
- `precision/<repo>-r1.json`: per-fix verdict, test check and upstream match for the sandboxed runs.

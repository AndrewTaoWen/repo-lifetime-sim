# Replaying upstream's real history onto agent-hardened code

**Question.** Hardening agents change a lot of code (200 to 950 changed lines per run). Does that make the project's real later changes harder to land? This is a first, purely mechanical maintainability measure.

**Answer.** Each run collided with 4 to 18 of upstream's later commits: 136 of 900 run × commit pairs (15%), almost all in package code. The improved prompt from `../ab-test/` was no worse than the baseline: 1.5 vs 1.75 colliding commits per 100 changed lines. The conflicts can't be resolved mechanically. Taking upstream's side of every conflict leaves half-merged functions (undefined names, missing imports) in 11 of 16 runs, so every collision would need a person or an agent to resolve it.

## Method (`../replay.py`)

For each of the 16 A/B runs:

1. Commit the agent's patch on top of the snapshot in the clone. No checkout is needed.
2. For each first-parent upstream commit after the snapshot (17 to 115 per repo), do a 3-way merge of the agent commit with that upstream commit, using the snapshot as the base, and count conflict hunks.
3. Call an upstream commit a **collision** if it adds conflict hunks in some file compared with the previous upstream commit. These are the real changes a maintainer would have had to hand-merge with the agent's edits.
4. Separately, merge all of upstream's history at once, resolve every conflict in upstream's favour (`-X theirs`), and run HEAD's tests on the result.

## Results

| Repo | Upstream commits | Collisions, baseline r1, r2 | Collisions, improved r3, r4 | Changed lines (r1 to r4) |
|---|---|---|---|---|
| python-dotenv | 17 | 6, 4 | 5, 4 | 383, 213, 229, 246 |
| cattrs | 34 | 9, 9 | 5, 7 | 670, 825, 773, 717 |
| werkzeug | 59 | 18, 9 | 12, 13 | 838, 496, 756, 955 |
| pydantic-settings | 115 | 8, 7 | 11, 9 | 319, 248, 329, 345 |
| **Total** | 225 per run | **70** | **66** | 3,992 vs 4,350 |

- Collisions per 100 changed lines: 1.75 for the baseline arm, 1.52 for the improved arm. Final conflict hunks per 100 changed lines: 2.6 vs 2.4.
- 21 of the 136 collisions are upstream fixing a bug the agent had also fixed (9 baseline, 12 improved). Two fixes of the same bug are bound to conflict, so these are the good kind. The other 115 are agent edits getting in the way of unrelated upstream work.
- Within a repo, larger diffs tend to collide more (werkzeug: 496 lines → 9 collisions, 838 lines → 18), but not consistently.

**Merged-tree tests aren't a usable semantic measure yet.** After resolving with `-X theirs`, 11 of 16 runs fail some of HEAD's tests (up to 112). Spot checks of cattrs-r1, python-dotenv-r1, pydantic-settings-r1 and werkzeug-r2 show the failures are almost all half-merges: a function keeps the agent's half but loses the definition it relies on (`NameError`, `ImportError`, `UnboundLocalError`). That says the edits are tangled within files, but it doesn't show real behavioural interference. The counts are kept in `results.json` (`broken`), but they shouldn't be read as semantic regressions.

## Caveats

- These are textual conflicts only. Two edits can merge cleanly and still clash in behaviour; finding those needs a proper resolution step first (below).
- First-parent history is used, so a merged pull request counts as one upstream commit.
- 2 runs per arm and 4 repos.

## Files

- `results.json`: per run, the upstream commit count, collisions (with each colliding commit's subject and files), final conflict hunks, diff size and `broken` tests.
- `../replay.py`: the script; `python3 replay.py --screen SCR --patches ../ab-test/patches --out results.json [--tests] runs...`

## Next

- Have an agent resolve each run's conflicts, then run HEAD's tests. That separates real behavioural clashes from the half-merges above, and measures the cost of resolving conflicts (time, tokens, success rate).
- Add a "small, local diff" instruction to the hardening prompt, and check whether collisions per run drop without losing recall.

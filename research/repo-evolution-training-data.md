# Is anyone building training data for how repos evolve over their lifetime?

*Researched 2026-10-18. Short answer: yes, but mostly as benchmarks; training data at "repo lifetime" scale is early and largely unpublished.*

## 1. The gap is real and now measured

A wave of 2025–2026 benchmarks replays real commit/release history so an agent must keep extending its *own* code, and they all show the same thing: agents that do well on isolated tasks fall apart as the codebase evolves.

| Benchmark | Built from | Scale | Headline result |
|---|---|---|---|
| [SWE-CI](https://arxiv.org/abs/2603.03823) | Base/target commit pairs, avg 233 days and 71 commits apart, replayed as up to 20 CI rounds | 100 tasks, 68 Python repos, 20 models | Scores future rounds more heavily ("EvoScore") so early tech debt is punished. Most models resolve under half; regressions grow over iterations. Explicit goal: "write code that lasts." |
| [SWE-Milestone / EvoClaw](https://www.alphaxiv.org/abs/2603.13428) | "DeepCommit" pipeline turns git history into a DAG of milestones; agent works in one persistent codebase | 98 milestones, 7 repos, 5 languages | >80% on isolated tasks drops to ≤38% continuous; precision plateaus early, read as accumulated tech debt. |
| [SWE-Chain](https://arxiv.org/abs/2605.14415) (NeurIPS 2026) | Consecutive package releases; each upgrade builds on the agent's previous output | 12 chains, 9 packages, 155 version transitions, 1,660 tasks | Best config (Claude Opus 4.7 + Claude Code) ~61% resolve; average ~45%. |
| [SWE-EVO](https://arxiv.org/abs/2512.18470) | Release notes of 7 Python libraries | 48 tasks, ~21 files each | GPT-5.4 + OpenHands solves 25% vs ~73% on SWE-bench Verified. |
| [ChainSWE](https://www.alphaxiv.org/abs/2607.02606) | Chained multi-bug maintenance | (not read in detail) | Same theme. |

Real-world evidence that the gap matters: [Debt Behind the AI Boom](https://arxiv.org/abs/2603.28592) traced 302k AI-authored commits across 6,299 GitHub repos; 15–29% of commits per assistant introduced an issue (89% code smells), and ~23% of those issues were still present at the latest revision.

## 2. Training data that exists today (mostly one step deep)

- **Commit / PR corpora.** [CommitPack](https://arxiv.org/abs/2308.07124) (4TB of commits, BigCode) and [SWE-RL](https://arxiv.org/abs/2502.18449) (Meta; RL on GitHub PR "software evolution" data) learn from history, but each example is a single diff, not a trajectory over the repo's life.
- **Synthetic task generators.** [SWE-smith](https://arxiv.org/abs/2504.21798) (Princeton/Stanford, NeurIPS 2025 spotlight) mass-produces bug-fix tasks by breaking working repos. Scales data, but each task is still one-shot.
- **Agentic mid-training.** Meta's [CWM](https://ai.meta.com/research/publications/cwm/) mid-trains on execution traces and agent trajectories in real repos. Again per-task, not per-lifetime.
- **Synthetic development process.** [Understanding by Reconstruction / Repo2Agent](https://arxiv.org/abs/2603.11103) (ByteDance Seed, Fudan, M-A-P; Mar 2026) has agents reverse-engineer the plan → reasoning → file-writing trajectory behind existing repos, and pretrains on that. Closest published thing to "synthetic repo construction data," but it reconstructs how a repo was *built*, not how it *changed* over years. Gains at 8B scale are modest.
- **Feature-tree synthesis** ([Microsoft Research](https://www.microsoft.com/en-us/research/articles/feature-tree-driven-synthesis-improves-training-data-for-code-llms/)) and [next-edit prediction](https://arxiv.org/abs/2508.10074) are adjacent: structured synthetic code and edit-history modeling, not lifetime evolution.

## 3. What labs have said

- I found **no public disclosure** from Anthropic, OpenAI, or Google DeepMind of a dataset or pipeline specifically simulating repo lifetimes. Evidence here is thin.
- Inference, not confirmed: the benchmark builders above (DeepCommit, SWE-Chain's DecompSynth, SWE-CI's commit-pair pipeline) are effectively RL environments. Any of them can be turned into multi-round training environments, and frontier labs routinely train on SWE-style environments, so it's likely some of this is happening privately. The fact that Claude Opus models lead SWE-CI and SWE-Chain is consistent with that but doesn't prove it.

## 4. Where the open space is

1. **Lifetime-scale trajectories.** Existing work stops at ~20 rounds or ~10 releases. Nothing public simulates years of growth (team turnover, requirement churn, scaling a 1k-LOC repo to 100k).
2. **Reward signal for "future-proof."** SWE-CI's future-weighted score is the only published reward that directly penalizes tech debt. Most others reward only current tests.
3. **Synthetic forward simulation.** Everything above replays *real* history. Generating plausible *future* requirements for a repo (so a model can be trained on code that survives changes it hasn't seen yet) appears largely unexplored in public work. This is the most direct answer to the original question, and the least covered.

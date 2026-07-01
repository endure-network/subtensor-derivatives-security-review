# batches/

One isolated directory per security batch. To start a new batch:
```bash
cp -r _TEMPLATE batch-NN-<slug> && $EDITOR batch-NN-<slug>/brief.md
```
Work only in your dir; use `../../tooling/`. Register confirmed findings in `../../FINDINGS.md`.

**Unbiased rule:** read `../../CONTEXT/` first and form your own hypotheses before opening any sibling batch's
`finding.md` / `summary.md`. They are spoilers.

| dir | area | status |
|-----|------|--------|
| `batch-01-selfcover-weights` | F-01 self-cover / open pricing-curve asymmetry | done — MEDIUM, dormant |
| `batch-02-cold-ema` | F-02 cold-EMA capacity bypass | done — MEDIUM; short + long confirmed; rollback probe rejected |
| `batch-03-emission-redirection` | L2 emission redirection + L2b pruning sabotage | settled — L2a LOW/infeasible; L2b LOW–MEDIUM confirmed (bounded) |
| `batch-04-coldkey-swap` | F-03 coldkey-swap derivative aggregate orphaning | done — MEDIUM |
| `batch-05-terminal-settlement` | F-04 short terminal settlement order dependence | done — MEDIUM |
| `batch-06-cross-state-drain` | F-02 cross-state drain composition (escalation probe) | settled — DEFENDED (not a drain); F-02 stays MEDIUM |
| `batch-07-hook-atomicity` | Non-transactional decay/dereg hook-transfer atomicity | settled — DEFENDED (no custody desync); 2 hardening notes |
| `batch-08-verification` | Independent verification round (2 blind auditors + 2 adversarial verifiers) | settled — all findings UPHELD, 0 overturned, 0 false positives; **F-04b** + **F-06** adopted |
| `batch-09-external-review-reconciliation` | Reconcile an independent full-PR code review (10 reviewers + adjudicator) | settled — corroborates F-02/F-03/F-06/χ; adopts **F-07** (HIGH DoS), **F-08**, **F-09**, **F-10**; F-06 → LOW→MEDIUM |

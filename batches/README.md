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
| `batch-03-emission-redirection` | L2 emission redirection | settled — LOW/infeasible; pruning sabotage remains candidate |
| `batch-04-coldkey-swap` | F-03 coldkey-swap derivative aggregate orphaning | done — MEDIUM |
| `batch-05-terminal-settlement` | F-04 short terminal settlement order dependence | done — MEDIUM |

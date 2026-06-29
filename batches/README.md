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
| `batch-02-cold-ema` | F-02 cold-EMA capacity bypass | done — MEDIUM; long-mirror + rollback in progress (parallel agent) |
| `batch-03-emission-redirection` | L2 emission redirection | in progress |

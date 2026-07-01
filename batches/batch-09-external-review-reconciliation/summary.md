# batch-09 — External full-PR code review reconciliation (summary)

**Type:** reconciliation / consolidation (not a new hunt). **Date:** 2026-07-01. **Status:** settled.

A separate **full-PR code review** — 10 first-pass reviewers across 4 provider families + security / tests /
maintainability / database specialists, evidence-adjudicated; **4 high / 14 medium / 12 low** — was run over the entire
#2764 diff. This batch reconciles it against our economic/reachability report. The review is archived here as
`external-review-PR-2764-2026-07-01.md`.

## Outcome
- **Corroborated** (independent, different method): F-02 (cold-start fallback), F-03 (rated **HIGH**), F-06 (rated
  **HIGH**), `executable_price_ppb`, and our χ/flow-dead conclusion (D-chi-moot).
- **Adopted 4 new in-scope defects** (all **re-verified against source** — code-level; structural/correctness, not
  economic PoCs):
  - **F-07 (HIGH)** — unbounded terminal-settlement iteration under a *fixed* dissolve weight → block-weight/liveness
    DoS. **Highest-severity item in the report**; composes with F-05 (prune-forced settlement).
  - **F-08 (MEDIUM)** — 1:1 exact-output fallback for non-dynamic pools; settlement never re-checks `mechanism==1` →
    possible unbacked payout.
  - **F-09 (LOW–MEDIUM)** — long terminal equity realized as *minted Alpha stake* then pro-rata distributed (dilution),
    vs shorts' direct-TAO payout.
  - **F-10 (LOW)** — `limit_price` binds the fee-less raw spot, not the fee+weight-aware realized price.
- **F-06 raised LOW→MEDIUM** — the `ShortTerminalSettled{equity}` event is emitted regardless of transfer success
  (off-chain reconciliation corruption).
- **Reconciled DEFENDED verdicts** (stand; hardening framing adopted): C-rollback (implicit vs explicit
  `#[transactional]`), C-atomicity (accounting-accuracy edges), D-chi-moot (χ=1 default write vs docs).
- **Out of scope** (acknowledged, not absorbed): ~16 code-quality / testing / weight-benchmark / documentation findings.

## Verification
Every adopted item is **code-level confirmed** with exact source anchors — see `finding.md`. Registered in
`../../FINDINGS.md` (F-07–F-10, F-06 bump, reconciliation rows) and rolled into `../../REPORT.md`
(§ "Cross-reference: independent full code review").

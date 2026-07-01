# batch-08 — Independent verification round (summary)

**Type:** verification / consolidation (not a new hunt). **Date:** 2026-07-01. **Status:** settled.

Four independent audit agents were run in parallel against #2764 head `1a7aa37`, each reproducing in the real
`pallet-subtensor` harness:
- **2 blind first-pass auditors** — given only `CONTEXT/`, withheld from `FINDINGS.md`/`REPORT.md`.
- **2 adversarial verifiers** — tasked to overturn every claim in the report.

## Outcome
- **All 6 findings (F-01..F-04, L2a, L2b) + all 3 defended probes UPHELD. 0 overturned. 0 false positives.**
- **F-04b (NEW, adopted):** the long terminal-settlement mirror is order-dependent — same `settle_longs_on_dereg`
  root cause as F-04 short. Confirmed by two independent PoCs.
- **F-06 (NEW, adopted, LOW):** unguarded equity transfer in `settle_shorts_on_dereg` can silently burn a sub-ED
  trader payout (then swept to issuance).
- **3 cross-state regimes positively defended** (previously "not separately reproduced"): amortized pump (best
  −0.826 TAO), regular in-kind close (best −0.0025 TAO), long-mirror cold-`A_ref` (best +3012 rao ≈ 0).
- **F-01 dormancy strengthened:** proportional emission is an exact fixed point at `w=0.5`; a seeded skew self-heals
  toward 0.5.

## Agents
| worktree | role | delivered | output |
|---|---|---|---|
| `fresh-opus` | blind auditor A | yes | `agent-outputs/auditor-fresh-opus--INDEPENDENT-AUDIT.md` |
| `fresh-gpt` | blind auditor B | **no** (context exhaustion / compaction) | — |
| `verify-opus` | adversarial verifier A | yes | `agent-outputs/verifier-verify-opus--VERIFICATION.md` |
| `verify-gpt` | adversarial verifier B | yes | `agent-outputs/verifier-verify-gpt--VERIFICATION.md` |

## Artifacts
- **Shipped PoC:** `../../tooling/poc/verification-round.patch` → `derivative_break_opus.rs` (7 tests, all pass:
  3 cross-state breaks defended, F-01 stability, independent F-02 cap-bypass, F-04 short + F-04b long).
- **Archived break harness** (verify-opus independent impl): `agent-outputs/verify-opus-break-harness.rs`.
- **Honesty note:** both opus-class harnesses first produced a spurious **+80,000 TAO** "drain" — a P&L-measurement
  bug (init captured *after* the manipulation stake); corrected (init before the pump) → nets ~0.

See `finding.md` for detail. Findings registered in `../../FINDINGS.md` (F-04b, F-06) and rolled into `../../REPORT.md`
(§ "Independent verification round").

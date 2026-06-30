# Batch 05 — Short terminal settlement order dependence (F-04)

**Verdict:** MEDIUM · confirmed · pre-launch · terminal fairness/accounting issue, not proven direct theft.

**One-liner:** `settle_shorts_on_dereg` restores each short position's escrow to the live subnet reserve immediately
before quoting that same position's terminal spot cover. Because settlement is sequential, later positions quote against
a pool already mutated by earlier positions. Identical short positions can receive different equity solely due to
storage/coldkey order.

**Proof:** `terminal_settlement_pays_identical_shorts_different_equity` inserts two identical short positions and
settles them during deregistration. Observed local output: first equity `332745565022` rao, second equity
`277162020499` rao.

**Severity:** terminal payout distribution is not position-symmetric and split-vs-merged exposure can differ at
deregistration. This can redistribute equity among derivative holders, but direct pool theft was not proven and the
feature is pre-launch.

**Files:** `finding.md`. **Fix:** quote all terminal positions against a common reserve snapshot, or restore all terminal
escrow/aggregate state before any per-position quote.

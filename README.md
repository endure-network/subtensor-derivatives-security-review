# Subtensor Covered Derivatives — Security Review Harness

A multi-batch security-research workspace for the **covered continuous-unwind short/long derivatives** in
[opentensor/subtensor#2764](https://github.com/opentensor/subtensor/pull/2764)
(client [latent-to/btcli#1007](https://github.com/latent-to/btcli/pull/1007)).

It is designed to run **multiple parallel, independent security batches** against the same target. Each batch gets
the full **unbiased context** it needs (facts + how-to + tooling), works in its own isolated directory, and registers
confirmed findings in a shared ledger.

> Feature status: `ShortsEnabled`/`LongsEnabled` default-OFF, not on mainnet — **pre-launch review**.

## How to run a security batch (the contract)
1. **Read `CONTEXT/` first** — it is *ground-truth facts and how-to*, deliberately free of conclusions.
2. **Form your own hypotheses** before reading any sibling batch's `finding.md`/`summary.md` or the verdicts in
   `FINDINGS.md` (see `METHODOLOGY.md` → "Staying unbiased"). `CONTEXT/05-open-surface.md` lists *leads* (questions),
   not answers — you may disprove them.
3. **Work in `batches/<your-batch>/`** (copy `batches/_TEMPLATE/`). Use `tooling/` (PoC harness patch, sims, probes).
4. **Verify before you claim** — reproduce in the Rust harness, settle numbers by running code, and check
   *live-state reachability* (a real defect can be dormant; see `CONTEXT/04-verified-facts.md`). Calibrate severity honestly.
5. **Register** any confirmed finding in `FINDINGS.md` and write it up in your batch dir.

## Layout
- `CONTEXT/` — unbiased ground-truth: target+scope, how-it-works, substrate, build/test/tooling, verified facts, open surface.
- `METHODOLOGY.md` — the assessment playbook + the unbiased-batch protocol + anti-patterns.
- `tooling/` — shared tools: `poc/derivatives-poc.patch` (harness tests), `sims/` (closed-form models), `probes/` (live-mainnet).
- `batches/` — one isolated dir per batch (`_TEMPLATE/` to start; `batch-01..` are done/in-progress).
- `FINDINGS.md` — the shared findings ledger (severity, status, owner).
- `REPORT.md` — the consolidated submission report (rolls up confirmed findings).
- `methodology/` — raw research journals from batch-01/02 (provenance; not required reading).

## Target code
The subtensor PR #2764 checkout is the parent dir (`/projects/subtensor`). For an external clone, see
`CONTEXT/03-build-test-tooling.md` to fetch it (`git fetch origin pull/2764/head`) and apply `tooling/poc/derivatives-poc.patch`.

## Disclosure
Findings concern a pre-launch feature and are currently non-exploitable on mainnet. **Private pending coordinated
disclosure / bug-bounty submission.** Do not redistribute.

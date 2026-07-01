# Methodology — how to run a security batch

## The playbook (every finding passes these gates)
1. **Ground in the code.** Read the actual extrinsic + the math it calls. Never reason about unread code.
2. **Model it closed-form.** Settle "is X profitable / conserved" with a runnable script (`Decimal`, see
   `tooling/sims/`) before writing chain code. Establish the baseline (e.g. `K0=N`) so you know what "no bug" looks like.
3. **Prove it in the real harness.** Reproduce in the project's own mock-runtime tests
   (`cargo test -p pallet-subtensor`, real pallet + real swap engine). A failing conservation assertion or a passing
   exploit assertion *is* the proof. Start from `tooling/poc/derivatives-poc.patch`.
4. **Check live-state reachability.** A real code defect can be **dormant**: verify whether the precondition actually
   occurs in production (e.g. `tooling/probes/probe_mainnet_weights.py`). Never report severity without this gate.
5. **Sweep for amplifiers.** Check recent/in-flight PRs that could arm a dormant defect (template:
   `batches/batch-01-selfcover-weights/amplifier-assessment.md`).
6. **Calibrate severity honestly.** Impact × reachability. Distinguish "exploitable today" from "latent/pre-launch."
   Over-claiming is a failure; so is dismissing a high-impact latent bug as LOW.

## Staying unbiased (why batches are isolated)
The value of parallel batches is *independent* coverage, so avoid anchoring:
- Read `CONTEXT/` (facts) but treat `batches/*/finding.md` and `FINDINGS.md` verdicts as **spoilers** — form your own
  view of the surface first, then cross-check to avoid pure duplication.
- `CONTEXT/05-open-surface.md` gives *leads* (questions), not answers.
- Re-verify any shared "fact" that is load-bearing for your finding — the verified-facts doc includes repro steps for this.

## Parallel execution — isolate the target checkout (learned in batch-08)
Running multiple agents at once buys throughput, but they must **not** share the target working tree. In the batch-08
verification round all four agents compiled against the same `/projects/subtensor`, so their PoC test files collided:
two agents independently created `derivative_break_opus.rs` (the on-disk file became whichever wrote last), and one
agent's report leaked into the target repo root. The findings survived (each agent kept a private copy and results
converged), but a `cargo test` run could silently compile another agent's tests. **Rule:** give each parallel agent its
own checkout (`git worktree add` per agent), or at minimum a unique PoC-filename namespace per agent, and treat the
shared target tree as read-only scaffolding. The deliverable repo (`security-review/`) is safely worktree-isolated; the
gap is the Rust target tree it points at.

## Anti-patterns (learned on this target)
- **Precondition smuggling:** claiming an exploit from a PoC that *set up* the precondition with a test helper, without
  checking it is reachable in production. (F-01 looked CRITICAL until the live-weights probe showed all pools at 0.5/0.5.)
- **Unrealistic forcing:** driving an input the real system never produces (e.g. a disproportionate emission injection
  that real proportional emission never makes).
- **Severity before reachability:** reporting HIGH/CRITICAL before the live-state + amplifier gates.
- **Trusting `lsp`/compile-green as "works":** behaviour must be exercised; run the test, read the numbers.

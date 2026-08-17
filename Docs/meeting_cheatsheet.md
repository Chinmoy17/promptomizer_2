# Meeting Cheat-Sheet — FDPO (read during the meeting)

*One page. Bold = say the number out loud. Full detail in [meeting_briefing.md](meeting_briefing.md).*

---

## Say these three things first
1. **The method works where theory predicts.** Vague one-liner → structured
   CoT prompt, regression-safe. **Hearsay +8.5 pp, 3/3 seeds, zero variance.**
   Reasoning MMLU: **math +5.6, philosophy +4.0, econ +2.0.**
2. **We found a clean empirical law** — CoT is a **double dissociation**: helps
   computation, **hurts factual recall**. Novel, defensible, paper-worthy.
3. **Ready to move to TAMUK open models** with **zero code changes — `.env`
   only.** Determinism + headroom should make gains bigger and CIs trustworthy.

---

## Key numbers (glance table)

| Result | Number |
|---|---|
| LegalBench-hearsay | 62.7 → **71.2 (+8.5)**, 3/3 seeds, spread 0.0 |
| MMLU math / philosophy / econ | **+5.6 / +4.0 / +2.0** |
| MMLU macro (current) | **+0.4 (flat)** — one regression cancels the gains |
| computer_security (near ceiling) | **−8.6** — the problem to fix |
| Double dissociation (direct→CoT) | math −5.3→**+5.6**; law +9.3→**−1.0** |
| Self-selected reasoning (baseline tokens) | math **434**, recall subjects **4–12** |

---

## The story of the flat macro (don't hide it)
- Reasoning subjects **gain**; near-ceiling recall subjects **regress**.
- Security: **0 fixed, 4–8 broken** every seed → over-reasoning breaks recall.
- **It's a gate/threshold issue, not an idea failure** — two clean fixes ↓.

## Two concrete fixes to propose
- **`--tau 5` (min mistakes) instead of 3** → near-ceiling subjects *skip*
  optimization (security ~3 fails, biology ~4). Failure-count based, **not** an
  accuracy hack. Would prevent −8.6 → **macro ~+1.8.**
- **`--simple-max-rounds 2` instead of 3** → round 1 usually wins; same accuracy,
  −33% cost. Confirm both by ablation.
- *(Coded, not yet validated: subject-adaptive optimizer = CoT for compute,
  direct for recall.)*

---

## TAMUK / Ollama — the one-liner answer
- **No code changes.** Client picks Azure vs OpenAI from `.env`
  (`api_version` set → Azure, else → `OpenAI(base_url)`).
- Edit `.env`: `SOLVER_BASE_URL=http://localhost:11434/v1`, `API_KEY=dummy`,
  **remove all `AZURE_OPENAI_*`**. Then `ollama pull llama3:8b-instruct`.
- Scripts: `pytest` → `--dry-run` → tiny real run → replicate hearsay → MMLU
  per subject. (`--budget-usd 0`, `--max-workers` = vLLM `--max-num-seqs`.)

---

## Paper direction — present both, let him steer
- **Framing A — Empirical study:** *"When does prompt optimization help?"* FDPO
  is one instrument among several. More novel, lower "did-you-beat-SOTA" risk.
- **Framing B — New method:** FDPO is the contribution; others are baselines.
- Needs either way: **3+ optimizers** (FDPO + APE/OPRO/TextGrad/DSPy), **3+
  datasets** (LegalBench, MMLU, GSM8K), **2 models** (Llama + gpt-4o-mini),
  3 seeds, significance tests.

---

## Honesty guardrails (so I don't overclaim)
- MMLU macro is **flat right now** — the win is per-subject + hearsay.
- Double dissociation is the strongest result but comes from **two different
  runs** (confound to close).
- Subject-adaptive fix is **coded, not validated** — last pilot didn't finish.
- Azure is **~5 pp noisy** at temp 0 — a reason to move, not a result.

---

## Questions to ask him
1. Paper framing: **empirical study** or **new method**? (leaning A)
2. Which baselines can we run at TAMUK — APE / OPRO / ProTeGi / TextGrad / DSPy?
3. Compute budget: how many GPUs, which Llama sizes?
4. Target venue / deadline?
5. Lead dataset: **LegalBench** (clean single win) or **MMLU** (per-subject story)?

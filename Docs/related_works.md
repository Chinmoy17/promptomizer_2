# Related Works — Quick Reference for FDPO

**Scope:** Only the works directly relevant to the proposed direction (modular,
feedback-driven, regression-gated prompt optimization). The full taxonomy and
30+ method survey is in [literature_survey.md](literature_survey.md).

---

## 1. Why This Document

Three lines of work intersect at the location FDPO targets:

1. **Modular prompt optimization** — decompose a prompt into semantic sections
   and optimize each section independently (MPO, aPSF, SAMMO).
2. **Regression-safe iterative optimization** — gate every update against a
   held-out batch, roll back if accuracy degrades (Trace2Policy / EISR).
3. **LLM-as-optimizer iterative refinement** — a critic LLM rewrites prompts
   based on validation feedback (PromptWizard, ProTeGi, TextGrad, OPRO).

Each line has at least one strong recent paper; **no single method combines all
three**. That is the gap.

---

## 2. The Modular Family

### 2.1 MPO — Modular Prompt Optimization

| Field | Value |
|---|---|
| Citation | Sharma & Henley, **Jan 2026** (CMU) |
| arXiv | [2601.04055](https://arxiv.org/abs/2601.04055) |
| Mechanism | Fixed 5-section schema + section-local textual gradients + LLM de-duplication |
| Schema | System Role / Context / Task Details / Constraints / Output Format |
| Solver models | LLaMA-3-8B-Instruct, Mistral-7B-Instruct (2 only) |
| Datasets | ARC-Challenge, MMLU (2 only; both multi-choice) |
| Baselines | TextGrad + untuned prompt (2 only) |

**Reported numbers**

| Dataset | Solver | Untuned | TextGrad | MPO | MPO Δ |
|---|---|---|---|---|---|
| ARC-Challenge | LLaMA-3-8B | 75.00 | 75.60 | **79.10** | +4.10 |
| ARC-Challenge | Mistral-7B | 70.73 | 70.30 | **73.04** | +2.31 |
| MMLU | LLaMA-3-8B | 57.21 | 56.40 | **61.50** | +4.29 |
| MMLU | Mistral-7B | 53.79 | 53.70 | **55.50** | +1.71 |

**Precise drawbacks** (read from §3 and §5 of the paper):

| # | Drawback | Severity |
|---|---|---|
| D1 | **No regression gate**. Updates are additive + de-duped; no mechanism to verify the update does not break previously-correct cases. | High |
| D2 | **No section-error attribution**. The critic is asked to critique every section every round; there is no signal saying "this failure was caused by section *k*". | High |
| D3 | **No failure examples fed to the critic**. The optimizer never sees the actual outputs that failed. ProTeGi's primary signal is missing. | High |
| D4 | **Fixed 5-section schema, hard-coded**. Cannot adapt to extraction, dialogue, or code tasks where structure differs. | Medium |
| D5 | **No stopping criterion**. "Number of iterations depends on prompt and task." | Medium |
| D6 | **Tiny experimental scope** — only 2 solver models, both 7–8B open-source; only 2 benchmarks, both multi-choice. | High |
| D7 | **Weak baseline panel** — no PromptWizard, GEPA, OPRO, ProTeGi, MIPROv2, SAMMO comparison. | High |
| D8 | **No reasoning / code / extraction benchmarks** — Output Format section cannot be stressed on A/B/C/D tasks. | High |
| D9 | **No statistical significance**. Single numbers; no seeds, no CIs, no paired tests. | Medium |
| D10 | **Critic model not even specified**; future-work explicitly notes a critic-strength ablation is missing. | Medium |
| D11 | **De-duplication unanalyzed**. No ablation; could erase semantically important distinctions. | Medium |
| D12 | **Entirely offline**. Assumes a labeled training set; no runtime feedback loop. | High |
| D13 | **No theoretical justification of the 5-section schema** — taken from OpenAI/Anthropic prompting guides. | Low |

### 2.2 aPSF — Adaptive Prompt Structure Factorization

| Field | Value |
|---|---|
| Citation | Liu et al., **Apr 2026** |
| arXiv | [2604.06699](https://arxiv.org/abs/2604.06699) |
| Mechanism | Architect model auto-discovers semantic factors; interventional factor-level scoring estimates each factor's marginal contribution; error-guided factor selection routes updates to the dominant failure source. |
| Reported gain | +2.16 pp avg accuracy; 45–87% token reduction on MultiArith |

**Strengths relative to MPO:**
- Auto-discovers structure (fixes MPO D4)
- Uses **interventional scoring** to find the dominant failure source — closer to section attribution (partially fixes MPO D2)
- More sample-efficient

**Remaining drawbacks:**
- Still **offline** (needs labeled training data)
- Still **no regression gate**
- Validation-performance scoring is *post-hoc*; the critic still doesn't see *which examples failed* directly

### 2.3 SAMMO — Structure-Aware Multi-Objective Metaprompt Optimization

| Field | Value |
|---|---|
| Citation | Schnabel & Neville, **EMNLP 2024 (Findings)** (Microsoft) |
| arXiv | [2404.02319](https://arxiv.org/abs/2404.02319) |
| Mechanism | Parses prompts into labeled component trees (`#instr`, `#format`, `#examples`); defines mutation operators per component type; beam search over the tree. |
| Code | https://github.com/microsoft/sammo (758 ★) |

The grandfather of the modular family. MPO and aPSF both build on this lineage. Notable property: produces noticeably **shorter** prompts at parity accuracy. Offline only.

### 2.4 Summary of the Modular Family

| Method | Year | Schema | Section attribution | Regression gate | Failure-example signal | Online |
|---|---|---|---|---|---|---|
| SAMMO | 2024 | Tagged tree | ✗ | ✗ | ✗ | ✗ |
| MPO | 2026-01 | Fixed 5 sections | ✗ | ✗ | ✗ | ✗ |
| aPSF | 2026-04 | Auto-discovered | partial (interventional) | ✗ | ✓ | ✗ |
| **FDPO (proposed)** | — | Configurable | **✓ judge-routed** | **✓ per-section** | **✓** | **✓** |

---

## 3. The Regression-Safe / Online Family

### 3.1 Trace2Policy / EISR — Error-driven Iterative Skill Refinement

| Field | Value |
|---|---|
| Citation | Zha, Wang, Zhou, Song (**SF Express**), **Jun 2026** |
| arXiv | [2606.10457](https://arxiv.org/abs/2606.10457) |
| Mechanism | Maintains a flat rule document. Each round: (1) execute on validation, (2) cluster errors into **MISSING / WRONG / CONFLICT**, (3) propose patches, (4) regression gate (>2% drop → discard), (5) best-snapshot fallback after 3 stagnant rounds. |
| Solver models | GLM-5, Kimi-K2.5, Qwen3.5-plus, MiniMax-M2.5, Claude Opus 4.6, Claude Haiku 4.5 (6 models) |
| Datasets | Logistics audit (proprietary, 3,349 cases over 22 days) + LegalBench hearsay + LegalBench contract_nli + LegalBench unfair_tos + BPIC 2012 |

**Reported numbers (logistics, 5-model average action accuracy):**

| Condition | Accuracy |
|---|---|
| B1b (zero-shot, no rules) | 70.3% |
| B5 (few-shot) | 73.3% |
| B7 (v1 unrefined rules) | 69.2% |
| **v8 (EISR-refined)** | **78.9%** |
| Compiled Python (production) | **79.6%** |

Auto-EISR matches Human-EISR on action accuracy at $5–$10 per cycle vs ~70 expert-hours.

**Crucial observation — Trace2Policy is NOT modular at the prompt level:**

Verbatim from §2: *"DSPy optimizes parametric prompt chains, whereas EISR refines an externalized, human-readable rule document amenable to compliance audit and version control."*

Their "modularity" lives in **error clustering** (MISSING/WRONG/CONFLICT), not in prompt structure. The optimized artifact is a **flat bullet list**.

**Strengths to borrow:**

| # | Strength | How FDPO uses it |
|---|---|---|
| S1 | Regression gate (>2% drop → discard) | Per-section regression gate |
| S2 | Best-snapshot fallback after stagnation | Per-section archive + rollback |
| S3 | MISSING/WRONG/CONFLICT error taxonomy | Judge's section attribution can use the same taxonomy |
| S4 | Online flywheel (≥5 similar errors trigger incremental refinement) | Threshold τ trigger |
| S5 | Pre-flight validator (mechanical checks before patch) | Same idea, applied per-section |

### 3.2 PromptWizard — Task-Aware Prompt Optimization Framework

| Field | Value |
|---|---|
| Citation | Agarwal, Singh, Dani et al. (**Microsoft Research**), May 2024 |
| arXiv | [2405.18369](https://arxiv.org/abs/2405.18369) |
| Mechanism | Self-evolving feedback-driven critique-and-synthesis; iteratively refines both instructions and in-context examples. |
| Evaluated on | 45 tasks across reasoning, classification, generation |

Strong feedback-driven baseline; not modular; offline. Cited by every recent
critique-based method as the SOTA single-prompt iterative refiner.

---

## 4. The Critique / Gradient Ancestors

| Method | Year | Mechanism | Why it matters |
|---|---|---|---|
| **ProTeGi** ([2305.03495](https://arxiv.org/abs/2305.03495)) | 2023 | "Textual gradient" critique on failure examples + beam search | First failure-driven prompt rewriter. Ancestor of FDPO's `LLMOptimize(p_old, E_fail, E_gold)` step. |
| **TextGrad** ([2406.07496](https://arxiv.org/abs/2406.07496)) | 2024 | LLM critique propagated through a computation graph; validation-based reversion | Has the only built-in *reversion mechanism* in the gradient family — but at graph-node level, not section level. |
| **OPRO** ([2309.03409](https://arxiv.org/abs/2309.03409)) | 2023 | Optimizer LLM observes (prompt, score) trajectory; proposes new candidates | The dominant LLM-as-optimizer pattern. Discovered "Take a deep breath…" prompt. |
| **GEPA** (ICLR 2026 Oral) | 2025 | Critique-conditioned evolutionary search + Pareto archive | Strongest dev-time evolutionary baseline; +6% over MIPROv2 with 35× fewer rollouts. |
| **APOHF** ([2405.17346](https://arxiv.org/abs/2405.17346)) | NeurIPS 2024 | Dueling-bandit over pairwise human preferences | The closest "feedback signal" cousin to FDPO. Pairwise, not section-level. |

---

## 5. Capability Matrix (the headline table)

| Capability | MPO | aPSF | SAMMO | Trace2Policy | PromptWizard | ProTeGi | TextGrad | **FDPO** |
|---|---|---|---|---|---|---|---|---|
| Section/component decomposition | ✓ fixed | ✓ auto | ✓ tags | ✗ | ✗ | ✗ | ✗ | **✓ configurable** |
| Section-error attribution by judge | ✗ | partial | ✗ | ✗ (whole-doc) | ✗ | ✗ | ✗ | **✓** |
| Failure examples feed the optimizer | ✗ | ✓ | partial | ✓ | ✓ | ✓ | ✓ | **✓** |
| Regression gate / rollback | ✗ | ✗ | ✗ | ✓ (whole-doc) | ✗ | ✗ | ✓ (graph-node) | **✓ per-section** |
| Best-snapshot archive | ✗ | ✗ | ✗ | ✓ (whole-doc) | ✗ | ✗ | ✗ | **✓ per-section** |
| Online / threshold-triggered | ✗ | ✗ | ✗ | partial (Phase 4) | ✗ | ✗ | ✗ | **✓ τ-trigger** |
| LLM-as-judge feedback signal | ✗ | ✗ | ✗ | ✗ | partial | ✗ | partial | **✓ binary + critique + section** |
| Solver models evaluated | 2 | several | several | 6 | several | 1 | 4 | proposed: 9 |
| Benchmarks evaluated | 2 | several | several | 5 | 45 | 4 | 6 | proposed: 8 |

---

## 6. Findings — What Each Paper Gives Us, What's Missing

| Finding | Source | Implication for FDPO |
|---|---|---|
| F1 — A fixed 5-section schema (Role / Context / Task / Constraints / Output Format) works on small open-source models. | MPO | Use this as the default schema; treat schema choice as a hyperparameter, not as the contribution. |
| F2 — Auto-discovered schemas (aPSF's "Architect model") give marginal gains and large cost reductions. | aPSF | Offer an "auto-schema" variant of FDPO as an ablation, not the headline. |
| F3 — In iterative refinement, **regression is real and costly**. Trace2Policy's R5 round dropped accuracy from 90% to 70% before the gate caught it. | Trace2Policy | The regression gate is **mandatory**, not optional. |
| F4 — A simple 2pp-drop threshold for the regression gate works in production. | Trace2Policy | Adopt the 2pp rule; ablate around it (1 / 2 / 5 pp). |
| F5 — Cluster-based error analysis (MISSING / WRONG / CONFLICT) reduces fix attempts from per-error to per-cluster, proportionally reducing regression risk. | Trace2Policy §3 | Use the same taxonomy for the judge's section attribution. |
| F6 — Best-snapshot rollback (after 3 stagnant rounds) prevents drift over long runs. | Trace2Policy Appendix M | Adopt at per-section level. |
| F7 — "Authority displacement": handing unrefined rules to strong models *hurts* them by 7–9pp (Opus, Haiku); weak models gain +22pp. | Trace2Policy §5.2 | Report results split by solver strength; expect non-monotone gains. |
| F8 — Compiled-Python execution of the *same* rule content beats LLM-prompt execution by 9.8pp in production. | Trace2Policy §4.1 | Compilation is orthogonal to FDPO; mention it but don't claim it. |
| F9 — On the MPO experimental scope (small open-source models, multi-choice QA), TextGrad sometimes **degrades** performance relative to the untuned prompt (MMLU LLaMA-3 8B: 57.21 → 56.40). | MPO §4.2 | Modular updates are more stable than monolithic — empirically supported. |
| F10 — Section-local updates with de-duplication outperform global TextGrad updates by 2–4pp on ARC and MMLU. | MPO §4 | Re-validate this on FDPO's broader benchmark suite; if it fails, that itself is a finding. |
| F11 — Auto-EISR (LLM-driven) matches Human-EISR (expert-driven) on action accuracy at ~1/100 the cost. | Trace2Policy §5.3 | LLM-as-judge as a substitute for human feedback is empirically supported. |

---

## 7. The Identified Gap (one sentence)

> **No published method combines (a) explicit prompt-section decomposition, (b) judge-routed section-error attribution, (c) per-section regression-gated updates, and (d) an online τ-triggered feedback loop with LLM-as-judge signals.** MPO has (a) only. aPSF has (a) + partial (b). Trace2Policy has (c) + partial (d) but not (a) or (b). FDPO is the first to combine all four.

---

*Companion documents:*
- [literature_survey.md](literature_survey.md) — full 30+ method academic survey
- [proposal.md](proposal.md) — research proposal with algorithm, datasets, experimental design

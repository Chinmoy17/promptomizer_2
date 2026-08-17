# Dataset Landscape and Strategic Decisions

**Purpose**: single-file discussion document for the professor meeting.
Consolidates (1) what each candidate benchmark actually is and how it is
conventionally used, (2) what our two comparison papers reported on each,
(3) where we stand, and (4) the concrete decisions we need input on.

**Companion docs** (for anyone who wants to drill down):
- [report.md](../report.md) — full pilot report with all our numbers
- [Tricks.md](../Tricks.md) — the honest list of what we can and can't do to move the number
- [Docs/fdpo_mechanism.md](fdpo_mechanism.md) — how our system actually works
- [Docs/running_on_local_gpu.md](running_on_local_gpu.md) — TAMU handoff runbook

**Reading time**: about 15 minutes.

---

## 1. The three benchmarks in play

We have three candidate benchmarks. They are very different from each
other in how they were built, what task they actually pose to the model,
and how they should be scored. This section is the shared vocabulary we
need before any strategic question makes sense.

### 1.1 ARC — AI2 Reasoning Challenge (2018)

**Origin story**: before ARC, question-answering benchmarks like SQuAD
and SNLI could largely be solved by surface-level word matching — many
datasets rewarded retrieval-style tricks rather than actual reasoning.
The Allen Institute for AI built ARC specifically to break that pattern
by using real, human-authored grade-school science exam questions
(arXiv:1803.05457).

**Structure**: 7,787 grade-school science questions, non-diagram,
multiple choice with four options (A–D). The clever part is the split:
- **Challenge Set** — 2,590 questions that *both* a retrieval-based
  algorithm and a word-co-occurrence algorithm fail to answer correctly.
  "Hard" is defined empirically, not subjectively.
- **Easy Set** — the remaining 5,197 questions.

Grade levels range from 3rd to 9th grade, so ages roughly 8–13. Example
of a Challenge question:

> "Which property of a mineral can be determined just by looking at it?
> (A) luster [correct] (B) mass (C) weight (D) hardness."

Trivial for a human, defeats retrieval-based baselines because the
answer isn't lexically present anywhere near "luster" in a supporting
document.

**Task the LLM is given**: 4-way multiple-choice classification.
Input = question + 4 options; output = one letter.

**Scoring**: exact-match accuracy on the letter. Never BLEU/ROUGE.

**Where our code stands**: we have ARC-Challenge downloaded to
`Dataset/arc_challenge/` (1,119 train / 1,172 test). We have never run
an experiment on it in this project.

### 1.2 MMLU — Massive Multitask Language Understanding (2021)

**Origin story**: Hendrycks et al. wanted a *breadth-over-depth*
benchmark — a knowledge-and-problem-solving stress test rather than a
reasoning trap like ARC. Explicitly designed for zero-shot and few-shot
evaluation, mimicking how humans are tested.

**Structure**: 15,908 multiple-choice questions across **57 subjects**
spanning STEM, humanities, social sciences, and professional domains
(from elementary to advanced professional difficulty). Standard split:
- **dev set** — 5 questions per subject (this is the origin of the
  "5-shot MMLU" reporting convention that became the de facto standard)
- **validation set**
- **test set**

**Task the LLM is given**: 4-way multiple-choice, options A–D.
Input = question + 4 options; output = one letter.

**Scoring**: average accuracy across subjects. Never BLEU/ROUGE.

**How the field's numbers have moved**: at release (2021), the three
smaller GPT-3 models scored ~25 % (random-guess floor for 4-way MC), the
175B GPT-3 model reached 43.9 % few-shot. Today, top models cluster at
86–89 %. The benchmark has a documented ~6 % error rate and ~13 points
of reproducibility variance in the published literature — worth knowing
because it directly affects what a "real" gain looks like on top-tier
models.

**Where our code stands**: we downloaded 6 subjects (professional_law,
philosophy, high_school_biology, econometrics, computer_security,
college_mathematics) to `Dataset/mmlu/` — 300 train / 2,469 test. We
have run 1 seed of `simple_fdpo` with all 6 subjects mixed. Result:
+1.4 pp aggregate, but the per-subject breakdown was the actual
finding (see §4 and report.md §6.3).

### 1.3 LegalBench — collaboratively-built legal reasoning benchmark (2023)

**Origin story**: unlike ARC and MMLU, LegalBench is *crowdsourced by
actual lawyers*, not scraped from an exam bank. Guha et al. at Stanford
+ collaborators. It is not one task — it is **162 tasks stitched into
one benchmark**, spanning six types of legal reasoning: issue-spotting,
rule-recall, rule-application, rule-conclusion, interpretation, and
rhetorical understanding.

**Construction philosophy**: tasks come from three sources. Many are
existing datasets (originally built for non-LLM evaluation) that were
significantly reformatted — for example, turning CUAD's span-extraction
contract dataset into a binary classification task suitable for LLMs.

**Split convention** (important, this is where LegalBench differs from
ARC/MMLU):

> "LegalBench deliberately does **not** follow a conventional ML train/
> test regime: the train split is small, usually fewer than 10 samples,
> following RAFT's design intent to provide labeled samples for few-shot
> demonstrations, while the test split is larger and used for
> evaluation. This is a *few-shot benchmark*, not a *fine-tune
> benchmark*."

Researchers who want traditional train/test splits are explicitly told
to combine and re-partition the data themselves. That is exactly what
we did: our LegalBench-hearsay 40 train / 59 test split is our own
re-carving of the 99 total examples, not the official 5 train / 94 test
split.

**Task types** (varies per subtask): binary classification, multi-class
classification, extraction, entailment, and short generation, across
statutes, judicial opinions, and contracts.

**Scoring** (varies per subtask):
- Most tasks: **balanced accuracy**. This matters because many legal
  tasks have skewed label distributions (e.g., "is this clause a
  non-compete?" — mostly "no"). Raw accuracy would flatter a
  majority-vote baseline.
- A handful of extraction/multilabel tasks: **F1**.
- Never BLEU/ROUGE.

**A parsing gotcha to flag**: at least one legal-domain fine-tune paper
(arXiv:2403.03883) noted that LegalBench in its current form can be
too stringent — some tasks score by the first predicted word expecting
Yes/No, so a slightly verbose but correct answer gets marked wrong. Any
generative system tested on LegalBench needs a lenient parser or must
document this as a limitation.

**Where our code stands**: we have LegalBench-hearsay only — 5 train /
94 test official, which we re-carve as 40 / 59 stratified across the 5
hearsay slices. We have run 3 seeds each under two mechanism
configurations. Best result: +4.0 pp mean across 3 seeds under 3-round
trajectory-best.

---

## 2. How prompt-optimization papers actually use these benchmarks

This is where a lot of confusion sits. The published field is
inconsistent, and comparing paper A's number to paper B's number
requires knowing what each paper actually did.

### 2.1 The re-partitioning convention

Across OPRO, EvoPrompt, PromptBreeder, DSPy/MIPROv2, "Knowing How to
Edit", Trace2Policy Auto-EISR — the pattern is uniformly:

1. **Ignore the benchmark's official split.** Carve your own train
   (where the optimizer/critic gets feedback) and test (where you
   report final numbers) partition sized to your compute budget.
2. **Report on your custom split**, sometimes disclosing sizes,
   sometimes not.

Examples we can verify:
- OPRO on BBH: "a subset of 20 % of examples is used for prompt
  optimization, and the rest for testing." On GSM8K: "a small subset of
  the training set is randomly sampled for optimization, and the entire
  test set is used for evaluation." (arXiv:2309.03409)
- "Knowing How to Edit" (arXiv:2511.19829, Chen et al.): "For each
  dataset, we randomly sample 100 examples for training and 100 for
  testing; for datasets with fewer than 200 samples, we adopt a
  50 % – 50 % train–test split." That is their protocol for all 8
  benchmarks including LegalBench definition_classification.

Consequence: **any headline number needs the associated split size to
be interpretable**. A +7 pp on 100 test items and a +7 pp on 2,000 test
items are not the same claim.

### 2.2 Scoring by task type

- **Multiple-choice tasks (ARC, MMLU, LegalBench MC subtasks)**:
  accuracy or balanced accuracy on the letter/label. Extraction on the
  final line via regex. Silent parse failures count as wrong.
- **Extraction / multilabel tasks (some LegalBench)**: F1.
- **Generation / summarization**: BLEU/ROUGE — but only appears when a
  paper mixes in a generation dataset (e.g. EvoPrompt reports SAMSum
  with ROUGE alongside its accuracy-scored classification datasets).
  **None of ARC / MMLU / LegalBench uses BLEU/ROUGE.**

---

## 3. What each comparison paper actually did

Two papers directly comparable to us. Their task menus differ.

### 3.1 Trace2Policy (arXiv:2606.10457, Zha et al., June 2026)

Their **primary contribution** is a real production deployment at SF
Express (a logistics carrier). Not a benchmark result. 22-day deployment
on 3,349 real audit cases, using compiled Python rules extracted through
their Error-driven Iterative Skill Refinement (EISR) mechanism.
Headline: 79.6 % accuracy on their compiled pipeline.

For prompt-optimization comparison purposes, they evaluate on **four
public benchmarks** as cross-domain probes:

| Task | Split | Executors tested | Their Auto-EISR result |
|---|---|---|---|
| LegalBench hearsay (§6, Table 5) | 30 iter / 64 held-out from 94 total | Opus 4.6 / Haiku 4.5 / Kimi K2.5 (**Human-EISR** results; see below) | Human-EISR: 92.2 / 93.8 / 90.6 % |
| LegalBench hearsay (Appendix I, Table 11) | 61 test | 3 executors (DeepSeek-v3.2 / Kimi-K2.5 / Kimi-K2.6), mean reported | Auto-EISR: 69.4 → 72.7 % (**+3.3 pp**) |
| LegalBench contract_nli | 71 test | same 3 executors, mean | Auto-EISR: 70.9 → 81.7 % (**+10.8 pp**) |
| LegalBench unfair_tos | 172 test | same 3 executors, mean | Auto-EISR: 84.1 → 81.4 % (**−2.7 pp**) |
| BPIC 2012 loan-decision | 297 test | same 3 executors, mean | Auto-EISR: 64.3 → 84.7 % (**+20.4 pp**) |

**The crucial distinction — Human-EISR vs. Auto-EISR:**
- **Human-EISR**: a *human* diagnoses errors and writes refinements.
  This is what produced the eye-catching 92-94 % hearsay numbers.
- **Auto-EISR**: an *LLM* replaces the human diagnostic step. This is
  the mechanism directly comparable to our `simple_fdpo` — both are
  fully automatic LLM-driven refinement.

**On the one task we share (LegalBench hearsay), the fair Auto-EISR
comparison is +3.3 pp, and ours is +4.0 pp. We are slightly ahead.**

The 92-94 % headline is comparing our automatic system to their
human-in-the-loop pipeline — not a fair apples-to-apples comparison.
We should stop citing those as our target.

### 3.2 Knowing How to Edit (arXiv:2511.19829, Chen et al., Nov 2025)

**Method**: trains an execution-free evaluator (LLaMA-3-8B + LoRA) that
predicts prompt quality from text directly, using four metrics
(negative log-likelihood, output stability, mutual information, query
entropy). Uses gradient-based attribution to identify what to rewrite.

**Split**: 100 train / 100 test per dataset (or 50/50 if the dataset
has fewer than 200 total). All methods evaluated with the same 3
executors and same max-3-iteration budget.

**Task menu**: 8 benchmarks — BBH×4 (causal_judgement,
disambiguation_qa, sports_understanding, web_of_lies), GPQA Diamond,
LegalBench definition_classification, MATH500, MedQA. MedQA and MATH500
are held-out (never seen during evaluator training).

**Their headline on the LegalBench task** (which is *definition*
classification, not hearsay — different LegalBench task):
- LLaMA-3-8B: 55 % → **70 %** (+15 pp)
- LLaMA-3.1-8B: 56 % → **69 %** (+13 pp)
- GPT-4o: 83 % → **90 %** (+7 pp)

**Critical caveat**: their method requires access to token
log-probabilities to compute NLL, stability, and mutual information.
**Azure OpenAI does not expose logprobs for gpt-4o-mini through the
standard chat/completions endpoint**, so this method cannot be
replicated on our current setup. It is directly runnable on open models
(LLaMA/Mistral via vLLM) — which is one of the arguments for the TAMU
handoff.

---

## 4. Where we stand — a single reference table

Our verified results across the three datasets we have touched:

| Dataset | Mechanism | Solver | Split | Seeds | Baseline (mean) | Final (mean) | Δ |
|---|---|---|---|:---:|---:|---:|---:|
| LegalBench hearsay | simple_fdpo (single-pass, pilot-era) | gpt-4o-mini | 40 / 59, stratified | 3 | 65.0 % | 72.3 % | **+7.4 pp** |
| LegalBench hearsay | simple_fdpo (3-round trajectory-best) | gpt-4o-mini | 40 / 59, stratified | 3 | 68.9 % | 72.9 % | **+4.0 pp** (best individual seed +6.8 pp) |
| MMLU (6 subjects mixed) | simple_fdpo (single-pass, pilot-era) | gpt-4o-mini | 120 / 150, stratified by subject | 1 | 59.3 % | 60.7 % | **+1.4 pp** (aggregate) |
| MMLU high_school_biology | (same run, per-subject cut) | gpt-4o-mini | subset of above | 1 | 78.9 % | 84.2 % | **+5.3 pp** |
| MMLU philosophy | (same run, per-subject cut) | gpt-4o-mini | subset of above | 1 | 68.4 % | 73.7 % | **+5.3 pp** |
| MMLU professional_law | (same run, per-subject cut) | gpt-4o-mini | subset of above | 1 | 51.6 % | 51.6 % | 0.0 pp (at chance) |
| GSM8K | simple_fdpo (single-pass) | gpt-4o-mini | 120 / 300, stratified | 3 | 93.8 % | 93.0 % | **−0.8 pp** (ceiling) |

**Total pilot spend across all runs**: about $3.

**Noise floor on Azure**: same-prompt re-runs at temperature 0 produce
3–5 pp of variance on our test sizes. This is not code non-determinism;
it is Azure's non-determinism, which does not exist on open models.
Directly limits how tight our confidence intervals can be until we move
to open-model deterministic inference.

---

## 5. The strategic picture: what to invest in next

**Working thesis**: LegalBench is our primary story. MMLU is deferred
until we have open-model deterministic inference. GSM8K is done. ARC is
optional.

### 5.1 Primary — broaden LegalBench

**Why**: our LegalBench-hearsay result (+4.0 pp mean, best individual
seed +6.8 pp) is defensible on its own but *one task is not a story*.
Trace2Policy tested on 4 tasks. "Knowing How to Edit" tested on 8. A
single-task result invites the reviewer question "did you cherry-pick
the task where your method works?" — a question we cannot answer with a
single data point.

**What tasks to add**: LegalBench candidates with enough test items to
support ≥3 seeds:
- `contract_nli` — binary entailment on contract clauses, ~500 test
  items, directly overlaps Trace2Policy's Auto-EISR probe
- `definition_extraction` — extract legal definitions from statutes,
  ~90+ test items, directly overlaps "Knowing How to Edit"'s
  definition_classification comparison
- `rule_qa` — short answer on legal rules, ~50 test items
- `hearsay` — already done, keep as anchor

Choosing 2 more (in addition to the hearsay we have) gives us a 3-task
family. Overlapping with what other papers tested makes our numbers
directly comparable.

**Estimated cost**: about $1.50 total, most of it in optimizer calls.
Wall time ~30 min per task per seed, so ~4-5 hours total for 2 new
tasks × 3 seeds each.

**Estimated effort**: 3-4 hours setup (writing `prompts/<task>.md`
seed prompts for each new task, verifying the extractor works on the
new output format, downloading and re-carving the splits) + the runtime
above.

### 5.2 Deferred — MMLU

**Why defer**: two independent reasons.

1. **Cost of doing it right is significant**. MMLU on the mixed
   6-subject configuration produced +1.4 pp aggregate — small, and
   likely not meaningful under Azure noise. The real finding is
   per-subject (biology +5.3, philosophy +5.3, law/math 0). To make
   that finding rigorous requires **one FDPO run per subject** — 6
   subjects × 3 seeds × 3 rounds = 54 runs at ~$0.15 each = ~$8. Not
   cheap, and Azure noise floor still contaminates individual subject
   results at ~19-93 items per subject.
2. **Open-model deterministic inference removes the noise floor**.
   Once TAMU is running Llama/Mistral via vLLM, MMLU per-subject
   becomes far cheaper (their GPU time, not our tokens) and more
   reliable (no Azure ~5 pp swings). Doing MMLU there is strictly
   better than doing it here.

**When to unblock**: the moment TAMU has their first LegalBench-hearsay
open-model run working end to end. Estimated: 2-3 days after handoff.

### 5.3 Deprioritized — GSM8K

**Why**: baseline is 93.8 % on gpt-4o-mini. The remaining 6 % is
structurally hard (multi-step arithmetic, unit conversion) and no
prompt rewording will fix a computational mistake. Our −0.8 pp result
is not a failure of the mechanism — it is a correct observation about
the capacity ceiling on this task with this solver. Keep it in the
report as the "here is what saturation looks like" data point, but
spend no more compute on it unless we switch to a much weaker solver.

### 5.4 Optional — ARC

**Why we haven't run it**: no seed prompt written, no direct
comparability advantage over LegalBench, and MMLU already covers the
"multi-domain multiple-choice" regime. But we have the data
(`Dataset/arc_challenge/`, 1,119 train / 1,172 test) and the ARC
Challenge Set is specifically designed to defeat surface-matching, so
it might complement MMLU in the "amplifier vs. injector" story.

Only add if the professor sees a specific value we haven't articulated.

---

## 6. Decisions we need input on

Six concrete questions. Yes/no or short-answer for each is enough.

### 6.1 Are we broadening LegalBench before or after the TAMU handoff?

- **Before** (this week): TAMU gets a repo with a 3-task family already
  demonstrated. Cost ~$1.50, wall ~4-5 hours.
- **In parallel**: TAMU starts on hearsay only; we broaden while they
  set up. Two forks of work that merge later.
- **After**: hand off single-task version now, add tasks later.

Recommended: **in parallel**. TAMU spin-up takes days regardless of
what code we send them.

### 6.2 Which 2 additional LegalBench tasks?

Preferred pair based on comparability to published work:
- `contract_nli` (overlaps Trace2Policy Auto-EISR probe)
- `definition_extraction` (overlaps "Knowing How to Edit" definition
  classification)

Alternative:
- `contract_nli` and `rule_qa` (broader task-type coverage)

Recommended: **contract_nli + definition_extraction**.

### 6.3 Do we drop the pilot-era +7.4 pp number from the headline?

The current [report.md](../report.md) shows both configurations
(single-pass +7.4 pp, 3-round trajectory-best +4.0 pp) side by side and
recommends citing the +4.0 pp as the headline. Alternative framings:

- **Keep both** (current state) — transparent but potentially confusing
  for a first-time reader
- **Cite only +4.0 pp** — cleaner headline, but discards a real data
  point we have on disk
- **Cite +6.8 pp** (best individual seed) — biggest single number, but
  cherry-picking (see [Tricks.md](../Tricks.md) §B1)

Recommended: **keep both, headline the +4.0 pp** (current state).

### 6.4 Do we correct the Trace2Policy comparison to be Auto-EISR-vs-us?

The current [report.md](../report.md) §7.1 compares our +4.0 pp to
Trace2Policy's Human-EISR numbers (92-94 %). The fair Auto-EISR
comparison is 72.7 % (+3.3 pp), which is slightly *below* our +4.0 pp
on the same task.

**Should the report emphasize this fair comparison** ("our automatic
mechanism matches or slightly exceeds their comparable automatic
mechanism on the shared task") rather than the current framing ("we are
at the low end of their published range")?

Recommended: **yes, update the report** — it is a stronger and more
honest positioning.

### 6.5 What triggers the TAMU handoff — right now, or after broadening?

- **Right now**: they get code today, start Llama-8B on hearsay
  immediately, parallel to our broadening work.
- **After 3-task broadening**: they get a stronger snapshot but wait ~1
  week.

Recommended: **right now, with a documented plan to pull additional
tasks as we finish them.**

### 6.6 Are we going to do open-model MMLU per-subject as a follow-up experiment?

This is the "amplifier not injector" finding as a proper experiment,
not a post-hoc analysis of one run. About 6 subjects × 3 seeds × 3
rounds = ~54 runs on a local GPU. Cost to us: $0 (GPU time only). Wall
time on Llama-3-8B: ~4-6 hours if run serially.

**If yes**: this becomes the strongest empirical claim in the paper,
because it demonstrates the mechanism-level finding across per-subject
baselines that span from chance (professional_law) to competent
(philosophy) to saturated (econometrics on gpt-4o-mini, though this
last will differ on Llama-8B).

**If no**: we stop after the LegalBench task-family result and treat
the MMLU per-subject finding as a preliminary observation to be
followed up in future work.

Recommended: **yes, but it happens at TAMU, not here.**

---

## 7. What we should NOT bring up (unless asked)

These are things that would derail the meeting more than help it:

- **Azure content filter tripping on MMLU professional_law** (~2 % of
  solver calls). Real but small; noted in report.md §3.
- **The exact per-round confusion matrix logs**. Available if asked but
  not central.
- **The Compactor Effect on frontier models with MIPROv2** (from
  earlier session notes). Not directly relevant to our current path.
- **The strict-rescue-vs-keep-best design debate**. Resolved this
  morning; keep-best won. Only worth explaining if the professor asks
  why our number moved from +7.4 to +4.0 between report versions.

---

## 8. TL;DR of the strategic picture

- **LegalBench-hearsay** is our anchor task. Result: **+4.0 pp mean
  across 3 seeds**, best individual seed +6.8 pp. Directly comparable
  to Trace2Policy Auto-EISR (+3.3 pp) — we match or slightly exceed
  their comparable automatic mechanism.
- **Broaden to 2 more LegalBench tasks** (contract_nli,
  definition_extraction) before the paper draft. Cost ~$1.50, effort
  ~1 working day.
- **Hand off to TAMU today** for open-model runs. Do MMLU per-subject
  there, not here. Azure's non-determinism floor blocks a rigorous
  MMLU result on our end.
- **Do not rely on GSM8K or ARC** for headline numbers. GSM8K is at
  ceiling; ARC is untested and does not add a comparability story we
  don't already have.

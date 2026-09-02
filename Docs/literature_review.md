# Prompt Optimization: Master Literature Review

**Purpose:** a single, non-duplicated reference covering every prompt
optimization method relevant to FDPO, written so it can be lifted almost
directly into a paper's Background / Related Work section. It supersedes the
scattered coverage in [`literature_survey.md`](literature_survey.md),
[`related_works.md`](related_works.md), and
[`prompt_optimization_literature_study.md`](prompt_optimization_literature_study.md)
(all three remain on disk as archival detail, each now carries a banner
pointing here). The FDPO-specific critique of the four newest papers and the
experiment/finish plan live in
[`four_paper_grilling_and_finish_plan.md`](four_paper_grilling_and_finish_plan.md);
this document is the broader literature review that plan draws on. The
dataset/benchmark-centric companion, with one table per benchmark rather
than one section per method, lives in
[`datasets_and_benchmarks.md`](datasets_and_benchmarks.md).

**How to use this document:**

- Section 2 gives the taxonomy every later section is organized around.
- Sections 3-11 are the family-by-family review - read these to write a
  Related Work section, or to check a specific method's mechanism, datasets,
  models, and reported numbers before citing it.
- Section 12 is one consolidated capability/rigor matrix across every method.
- Section 13-14 are dataset and evaluation-protocol reference tables.
- Section 15 states the literature gap and positions FDPO honestly (aligned
  with the claim boundaries already established in the finish plan doc).
- Section 16 maps this work to the **SANER 2027 Agentic AI4SE Track**,
  including a fit gap that should be fixed before submission.
- Section 17 gives ready-to-adapt related-work paragraph templates.
- Section 18 is the master reference list.

---

## 1. Document map (read this first)

| Document | Role | Status |
|---|---|---|
| `literature_review.md` (this file) | Master literature review across all families; paper-ready prose + tables | **Canonical** |
| `datasets_and_benchmarks.md` | Dataset-first companion: one table per benchmark, every paper/method that reported on it, side by side | **Canonical**, complements this file |
| `four_paper_grilling_and_finish_plan.md` | Deep critique of PromptWizard/EvoPrompt/GEPA/survey vs. current FDPO code and results; experiment matrix; finish-line plan | **Canonical**, FDPO-specific |
| `literature_survey.md` | Original 30+-method taxonomy survey (June 2026) | Archival detail; superseded pointer added |
| `related_works.md` | Original modular/regression-safe-family quick reference (MPO, aPSF, SAMMO, Trace2Policy) | Archival detail; superseded pointer added |
| `prompt_optimization_literature_study.md` | Original dataset/protocol-heavy study, including three externally supplied reference papers | Archival detail; superseded pointer added |
| `proposal.md` | Research proposal / algorithm description | Unchanged; still the authoritative algorithm proposal narrative |

Going forward, add new methods to this file, not the three archival documents.

---

## 2. Scope and taxonomy

Automatic prompt optimization (APO) covers algorithms that search, refine, or
generate natural-language instructions (and, in hybrid settings, in-context
exemplars or continuous embeddings) for a frozen foundation model, without
updating model weights. Three axes organize the field and are reused in every
section below.

**Axis A - When optimization happens.**
*Offline*: a fixed labeled dataset drives one optimization pass before
deployment (the large majority of published methods). *Online*: optimization
runs continuously against live signals during deployment (rare; an explicit
open direction per the 2025 survey, Section 7).

**Axis B - What signal drives the optimizer.**
Task accuracy against gold labels (dominant); LLM-generated critique text
used as a gradient analogue; human ratings or preferences (rare, expensive);
multi-objective combinations (accuracy plus cost, length, faithfulness,
safety).

**Axis C - Optimization mechanism.**
Discrete search (enumeration, beam search, MCTS); gradient-inspired textual
differentiation; evolutionary search (mutation, crossover, Pareto retention);
Bayesian/model-based search (TPE samplers, surrogate preference models);
LLM-as-optimizer (a separate LLM proposes candidates from a trajectory or
error analysis); fine-tuning-based (a small model is trained to be the
optimizer itself).

| Axis | Values | Where FDPO sits |
|---|---|---|
| A | Offline / Online | Offline batch experiment today; online triggering is a stated but unimplemented future direction |
| B | Accuracy / Critique / Human / Multi-objective | Accuracy-triggered, with the raw failed solver trace (question, wrong output, reference answer) as the critique-analogue input |
| C | Search / Gradient / Evolutionary / Bayesian / LLM-as-optimizer / Fine-tuning | LLM-as-optimizer, single whole-prompt rewrite by default, optional multi-round validation-selected search |

---

## 3. Foundational works

These are the papers every later method cites as ancestor or baseline.

**AutoPrompt** (Shin et al., EMNLP 2020, arXiv:2010.15980) is the earliest
automatic prompt construction method: it uses gradient-based HotFlip-style
search over the vocabulary to find discrete trigger tokens that maximize a
masked language model's probability of the correct label. It requires
gradient access, so it only applies to small open models, and it produces
non-human-readable token sequences rather than instructions.

**Chain-of-Thought prompting** (Wei et al., NeurIPS 2022) and its **zero-shot
variant** (Kojima et al., NeurIPS 2022, the "Let's think step by step" trigger)
are not optimizers but are the universal baseline every later method must beat.
**Auto-CoT** (Zhang et al., ICLR 2023) automates CoT demonstration
construction by clustering training questions and generating one zero-shot CoT
rationale per cluster as a few-shot exemplar.

**APE** (Zhou et al., ICLR 2023, arXiv:2211.01910) frames prompt generation as
black-box search: an LLM proposes candidate instructions from a handful of
input-output demonstrations, candidates are scored on a small validation set,
and top candidates are iteratively paraphrased. On GSM8K it discovered a
stronger CoT trigger than the hand-written one, evaluated on the
Instruction-Induction and BIG-Bench-Instruction-Induction benchmarks with
text-davinci-001/002 as both generator and scorer. It performs one-shot
generation with no failure analysis and no multi-step pipeline handling.

| Method | Year | Mechanism | Output | Models |
|---|---|---|---|---|
| AutoPrompt | 2020 | Discrete gradient search | Trigger tokens | RoBERTa-base/large |
| CoT | 2022 | Manual demonstrations | Few-shot prompt | PaLM, GPT-3 |
| Zero-shot CoT | 2022 | Single trigger phrase | Zero-shot prompt | text-davinci-002, PaLM |
| Auto-CoT | 2022 | Cluster + sample | Few-shot prompt | text-davinci-002 |
| APE | 2022 | Generate + score + paraphrase | Instruction | text-davinci-001/002 |

---

## 4. Gradient-inspired / textual-gradient family

This family imports the abstraction of backpropagation into text: an LLM
produces a natural-language critique after observing failures, and a second
LLM call applies that critique as a rewrite.

### 4.1 ProTeGi (Pryzant et al., EMNLP 2023, arXiv:2305.03495)

ProTeGi is the paper that introduced the "textual gradient" and is the direct
conceptual ancestor of any method that shows the optimizer raw failures. Its
loop: run the current prompt on a 64-example minibatch, collect failures, send
them to a gradient-generator LLM that critiques the prompt's weakness, use
that critique to generate candidate rewrites, expand the pool by Monte Carlo
paraphrasing, and select via beam search (width 4, depth 6, 8 expansions per
parent) scored on validation accuracy. It reports on Ethos (hate speech, F1),
Liar (fake news, accuracy), a custom Jailbreak safety set, and Sarcasm
detection, using GPT-3.5-turbo as both gradient generator and scorer, averaged
over 3 runs, with F1 gains up to 31% over the initial prompt and 4-8% over
Monte-Carlo/RL baselines. ProTeGi requires labeled training data up front,
optimizes once offline, and has no threshold-triggered or versioned iteration.

### 4.2 TextGrad (Yuksekgonul et al., 2024, arXiv:2406.07496)

TextGrad generalizes ProTeGi into a full automatic-differentiation framework
for compound AI systems: a computation graph of text variables (prompts,
generated answers, tool outputs), with a backward pass that propagates
LLM-generated critiques from terminal nodes to every upstream variable, each
updated iteratively (up to 10 iterations) with a validation-based reversion
mechanism. It is evaluated on MMLU-ML, GSM8K, HumanEval, GPQA Diamond,
DOCKSTRING molecule generation, and a radiotherapy-planning case study, using
Claude-3.5-Sonnet as the backward/feedback model and GPT-4o-mini as the
forward/execution model, reporting roughly a 9-point improvement over
zero-shot GPT-4o on GSM8K. TextGrad is powerful but not drop-in: adopting it
requires redesigning a pipeline around its variable/node abstraction, unlike a
single markdown prompt rewrite.

### 4.3 Other members

**GLaPE** combines a ProTeGi-style textual gradient with an evolutionary outer
loop to resist the beam-search plateaus that pure gradient-style search can
stall in. **AutoHint** (Sun et al., 2023) summarizes a batch of failures into
reusable natural-language hints appended as few-shot guidance rather than
rewriting the instruction body. **CRISPO** (He et al., 2025) decomposes
critique into multiple aspects (style, precision, content alignment, format)
and aggregates aspect-specific suggestions into one update. **ETGPO**
(2026, arXiv:2602.00997) clusters failures into an explicit error taxonomy,
filters to the categories above a prevalence threshold, and generates one
actionable guidance sentence per category before combining them into a single
rewrite; it is still a one-shot offline method.

| Method | Feedback/optimizer LLM | Scorer/executor LLM | Update unit | Datasets | Metric |
|---|---|---|---|---|---|
| ProTeGi | GPT-3.5-turbo | GPT-3.5-turbo | Beam search over rewrites | Ethos, Liar, Jailbreak, Sarcasm | F1 |
| TextGrad | Claude-3.5-Sonnet | GPT-4o-mini | Graph-wide backprop | MMLU, GSM8K, HumanEval, GPQA, DOCKSTRING | Accuracy, Pass@1 |
| GLaPE | Variant-dependent | Variant-dependent | Population + gradient mutation | BBH, GSM8K | Accuracy |
| AutoHint | LLM | Task model | Hint injection | Failure batches (task-specific) | Task metric |
| CRISPO | LLM | Task model | Multi-aspect critique aggregation | Text generation tasks | Task metric |
| ETGPO | LLM | Task model | Taxonomy-guided single rewrite | BBH, GPQA Diamond, LegalBench definition classification | Accuracy |

**What FDPO shares with this family:** the whole idea of showing the optimizer
raw failed examples rather than a scalar score. **What FDPO does not yet do
that this family does:** ProTeGi/TextGrad both search a population of
candidate rewrites per round and select via beam search or graph-wide
backprop; FDPO's default is a single accepted candidate per round.

---

## 5. Evolutionary and search-based family

Evolutionary methods maintain a population of prompt candidates and apply
selection, mutation, and crossover; LLMs typically implement the mutation and
crossover operators, and fitness is a validation-set score.

### 5.1 EvoPrompt (Guo et al., ICLR 2024, arXiv:2309.08532)

EvoPrompt applies classical Genetic Algorithm (GA) and Differential Evolution
(DE) operators to prompt optimization, with an LLM performing the crossover
(combine traits of two parents) and mutation (paraphrase/modify one parent)
steps. It maintains a population of 10, runs 4 generations, and is evaluated
on 31 datasets spanning sentiment/topic/subjectivity classification (SST-2,
SST-5, AG's News, Subj, CR, MR, TREC), Instruction-Induction tasks, five BBH
subtasks, and generation tasks (SAMSum summarization, ASSET simplification),
using Alpaca-7B and GPT-3.5 as both task executor and evolutionary operator.
Reported aggregate: Alpaca classification average 77.05 versus APE's 73.80;
BBH average 75.03 versus a 71.49 zero-shot baseline; the DE variant is
generally more stable than GA. It uses **no failure-example signal at all** -
fitness is a scalar development-set score, which is the sharpest contrast with
FDPO, PromptWizard, and GEPA. Some of its reported best BBH prompts are
generic or semantically mismatched to the task, which is a caution against
treating "readable and high-scoring" as evidence of genuine task
understanding. The GPT-3.5 configuration is reported for a single seed.

### 5.2 PromptBreeder (Fernando et al., 2023, arXiv:2309.16797, DeepMind)

PromptBreeder co-evolves two populations: task-prompts and the
*mutation-prompts* that instruct how to mutate a task-prompt. Binary-tournament
selection replaces the loser with a mutated copy of the winner; mutation-prompts
are themselves periodically meta-mutated. Evaluated on GSM8K, SVAMP,
MultiArith, AddSub, AQuA, ASDiv, and instruction-induction tasks with PaLM 2-L,
it reportedly outperforms hand-engineered prompts and Auto-CoT on most
arithmetic benchmarks, with the self-referential mutation producing more
diverse exploration than fixed-operator methods.

### 5.3 GEPA (Agrawal et al., 2025, ICLR 2026)

GEPA combines reflective mutation with instance-wise Pareto candidate
selection. A reflective LLM is given full execution traces, evaluator
feedback text, and scores, and is asked to attribute success or failure to
specific prompt elements before proposing a revision; Pareto retention
maintains an archive of diverse strategies instead of always mutating one
global best, and an optional system-aware merge crosses over two lineages.
Evaluated on six task families (multi-hop QA, instruction following, fact
verification, privacy-aware delegation, and two math benchmarks) with Qwen3-8B
and GPT-4.1 Mini, GEPA outperforms GRPO (24,000 rollouts) by up to roughly 20
points using about 35x fewer rollouts, and beats MIPROv2 by an average of
about 6 points across six tasks, remaining sample-efficient with as few as
20-50 training examples; a Qwen-optimized prompt also transfers with a
measurable gain when evaluated unchanged on GPT-4.1 Mini. Caveats: the merge
operator is not uniformly beneficial (it reduces some Qwen aggregate results),
repeated Pareto-validation selection can still adapt to the validation set,
and GEPA needs a genuinely useful textual feedback function, which many
production failures do not supply for free.

### 5.4 PromptAgent (Wang et al., ICLR 2024, arXiv:2310.16427)

PromptAgent treats prompt optimization as Monte Carlo Tree Search over
expert-level prompts: each node is a prompt, each edge an LLM-proposed edit
conditioned on a sample of failure cases, with UCT back-propagation over
validation scores. Evaluated on six BBH subtasks and several biomedical NER
and relation-extraction datasets (NCBI, BC5CDR, ChemProt) plus Amazon product
classification and ISEAR emotion detection, using GPT-3.5-turbo as worker and
GPT-4 as optimizer, it reports roughly a 9-point average improvement over APE
and CoT baselines, especially strong in the biomedical domain, illustrating
that expert-level prompts benefit from injecting domain knowledge drawn
directly from observed failures.

| Method | Population | Selection | Mutation operator | Generations | Sees raw failures? |
|---|---|---|---|---|---|
| EvoPrompt (GA/DE) | Task prompts | Fitness | LLM crossover + mutation | 4 | No (scalar fitness only) |
| PromptBreeder | Task + mutation prompts | Binary tournament | Self-referential | Variable | No |
| GEPA | (instruction, exemplar) candidates | Pareto retention | Critique-conditioned mutation | Variable | Yes, full traces + feedback |
| PromptAgent | Tree of prompts (MCTS) | UCT | LLM edit from failures | 3x3 | Yes |

---

## 6. LLM-as-optimizer family

Here a separate LLM is the optimizer directly: it observes a trajectory of
(prompt, score) pairs or an error analysis and proposes new candidates, with
no explicit gradient or population machinery.

**OPRO** (Yang et al., ICLR 2024, arXiv:2309.03409) is the canonical example: a
meta-prompt contains the optimization-problem description, the top-20 past
(instruction, score) pairs, and 3 random training exemplars; the optimizer
samples 8 new candidates at temperature 1.0, each scored greedily at
temperature 0, for up to 100 steps (most tasks converge by step 20-40). On
GSM8K (about 261 of the 7,473 training examples used for optimization, full
1,319-example test set) and BBH (roughly 100 train / 200 test per subtask), it
reports up to an 8-point gain over human-designed prompts and beats zero-shot
CoT on 19 of 23 BBH subtasks by more than 5 points, with the now-famous
discovered prompt "Take a deep breath and work on this problem step-by-step."
OPRO has no failure-example signal, no versioning, and a static training set.

**PE2** (Ye et al., NAACL 2024, arXiv:2311.05661) studies GPT-4 optimizing
prompts for GPT-4 itself via a meta-meta-prompt, and its most citation-worthy
finding is that prompts optimized for one model transfer poorly to another
(text-davinci-003-optimized prompts underperform when moved to GPT-3.5,
Mistral-7B, or Yi-6B without re-optimization) - direct motivation for treating
cross-model transfer as an experiment, not an assumption.

Smaller members train a dedicated rewriter model instead of calling a frozen
LLM at inference time: **PRewrite** (RL/PPO-trained rewriter), **BPO**
(SFT-trained universal rewriter from preference data), and **FIPO**
(instruction-tuned rewriter specialized to AlpacaEval/MT-Bench-style tasks).
**StablePrompt** adds an explicit stability regularizer that penalizes
candidates with high cross-fold accuracy variance, addressing a documented
weakness of trajectory-based search.

A recurring, citation-worthy design pattern in this family is the **dual-LLM
discipline**: separate the model that proposes prompts (optimizer/critic,
usually high temperature) from the model that executes them (scorer/worker,
usually temperature 0), for cost, bias, and stability reasons, and to permit
transfer-capability ablations (PE2 explicitly studies this). A second
recurring pattern is the **meta-prompt template** itself, which falls into
three archetypes: trajectory-based (OPRO: "here is a list of past prompts and
scores, propose something better"), error-analysis-based (ProTeGi/GEPA: "here
are the specific inputs where you failed and why, propose a fix"), and
component-edit-based (SAMMO: "here is the labeled component tree, edit this
node to fix this weakness"). FDPO's optimizer prompt is squarely
error-analysis-based.

| Method | Meta-prompt style | Optimizer | Scorer | Sees raw failures? |
|---|---|---|---|---|
| OPRO | Trajectory | PaLM 2-L / GPT-3.5 / GPT-4 | PaLM 2-L / text-bison | No |
| PE2 | Meta-meta-prompt | GPT-4 | GPT-4, Mistral-7B, Yi-6B | Partial (error analysis instructions) |
| PRewrite | RL-trained rewriter | T5 / Llama-3-8B (PPO) | Task model | No |
| BPO | SFT-trained rewriter | Llama-2-7B | GPT-3.5/4, Llama-2 | Indirectly via preference data |
| FIPO | SFT-trained rewriter | Small LM | Instruction-tuned LLM | No |
| StablePrompt | Stability-regularized trajectory | LLM | LLM | No |

---

## 7. Framework-level optimizers

These are not standalone algorithms but libraries that wrap one or more APO
mechanisms as "compilers" for compound LLM pipelines.

**DSPy** (Khattab et al., ICLR 2024, arXiv:2310.03714) exposes
`dspy.Module`/`dspy.Signature`/`dspy.Predict` primitives and ships several
optimizers ("teleprompters"): `BootstrapFewShot` mines high-scoring traces as
few-shot demonstrations with no instruction search at all; **COPRO** is a beam
search over LLM-proposed instructions; **MIPROv2** (Opsahl-Ong et al., 2024,
arXiv:2406.11695) runs a three-stage pipeline - bootstrap demonstrations,
propose instructions from dataset summaries and bootstrap traces, then run
Bayesian search (Optuna TPE) over instruction/demonstration combinations,
using a 90/10 train/validation split with the test set untouched, 10-25
candidate instructions per predictor, and light/medium/heavy search budgets
(13/~50/~200+ trials); **SIMBA** performs online stochastic mini-batch ascent
over the same pipeline abstraction, reported as more sample-efficient than
MIPROv2 for pipelines with many predictors. TextGrad is also published as a
standalone library exposing its computation-graph abstraction directly.
MIPROv2 is the strongest, most cited framework-level baseline and the one GEPA
compares itself against directly.

| Framework | Optimizer | Mechanism | Requires pipeline rewrite? |
|---|---|---|---|
| DSPy | BootstrapFewShot | Trace mining | Yes |
| DSPy | COPRO | Beam search | Yes |
| DSPy | MIPROv2 | Bayesian (TPE) over instructions + demos | Yes |
| DSPy | SIMBA | Stochastic mini-batch ascent | Yes |
| TextGrad (as library) | TextGrad | Graph backprop | Yes |

---

## 8. Modular / structure-aware family

This family treats the prompt as a structured object (labeled sections or an
auto-discovered component tree) rather than a flat string, and optimizes
components individually.

### 8.1 SAMMO (Schnabel and Neville, EMNLP 2024 Findings, arXiv:2404.02319, Microsoft)

SAMMO parses a prompt into a labeled component tree (`#instr`, `#format`,
`#examples`, and similar tags), defines mutation operators per component type,
and runs beam search while tracking multiple objectives (accuracy, latency,
length) simultaneously. It reports matching or exceeding APE and OPRO on
classification, NER, and summarization while producing noticeably shorter
prompts, a direct structural side-effect of component-level optimization. It
is the conceptual grandfather of the modular family; it is offline only and
has no regression gate.

### 8.2 MPO - Modular Prompt Optimization (Sharma and Henley, Jan 2026, arXiv:2601.04055, CMU)

MPO uses a fixed five-section schema (System Role / Context / Task Details /
Constraints / Output Format), applies section-local textual gradients, and
de-duplicates the resulting edits with an LLM pass. It is evaluated on only
two solver models (LLaMA-3-8B-Instruct, Mistral-7B-Instruct) and two datasets
(ARC-Challenge, MMLU), against an untuned baseline and TextGrad, reporting
consistent gains (for example ARC-Challenge LLaMA-3-8B: 75.00 to 79.10; MMLU
LLaMA-3-8B: 57.21 to 61.50). Its own text and structure expose several precise
gaps: **no regression gate** (updates are additive and de-duplicated with no
check that a previously-correct case is not broken), **no section-error
attribution** (the critic critiques every section every round rather than
being told which section caused a specific failure), **no raw failure
examples shown to the critic** (ProTeGi's primary signal is absent), a
**hard-coded schema** that cannot adapt to tasks whose structure differs, **no
stopping criterion**, only two solver models and two benchmarks (both
multiple-choice), a **weak baseline panel** (no PromptWizard, GEPA, ProTeGi,
or MIPROv2 comparison), and **no statistical rigor** (single numbers, no
seeds, no confidence intervals). The five-section schema MPO popularized is
also the schema FDPO's current markdown format is built on, which makes MPO
FDPO's closest structural ancestor and its most directly comparable baseline.

### 8.3 aPSF - Adaptive Prompt Structure Factorization (Liu et al., Apr 2026, arXiv:2604.06699)

aPSF auto-discovers semantic factors instead of using MPO's fixed schema,
scores each factor's marginal contribution via interventional (ablate-and-test)
scoring, and routes updates to the dominant failure source, reporting a +2.16
percentage-point average accuracy gain and a 45-87% token reduction on
MultiArith. It partially closes two of MPO's gaps (auto-discovered structure,
and interventional scoring as a step toward section attribution) but remains
offline, still has no regression gate, and its validation-performance scoring
is still post hoc rather than shown directly to the critic as raw failed
cases.

| Method | Year | Schema | Section attribution | Regression gate | Raw failure signal | Online |
|---|---|---|---|---|---|---|
| SAMMO | 2024 | Tagged tree | No | No | No | No |
| MPO | 2026-01 | Fixed 5 sections | No | No | No | No |
| aPSF | 2026-04 | Auto-discovered | Partial (interventional) | No | Yes | No |
| FDPO (current) | 2026 | Fixed 5 sections (markdown) | No (whole-prompt rewrite) | No default gate (validation selects, does not veto) | Yes (question + wrong output + gold) | No |

---

## 9. Regression-safe and online/production family

### 9.1 Trace2Policy / EISR (Zha, Wang, Zhou, Song, SF Express, Jun 2026, arXiv:2606.10457)

Trace2Policy (internally: Error-driven Iterative Skill Refinement, EISR)
maintains a **flat rule document**, not a modular prompt. Each round: execute
on a validation batch, cluster errors into a three-way taxonomy - MISSING
(a needed rule is absent), WRONG (a rule exists but is incorrect), CONFLICT
(two rules disagree) - propose patches per cluster, apply a regression gate
that discards a round if accuracy drops more than 2 percentage points, and
fall back to the best-known snapshot after 3 stagnant rounds. It is evaluated
on a proprietary logistics-audit stream (3,349 cases over 22 days) plus
LegalBench hearsay, LegalBench contract_nli, LegalBench unfair_tos, and BPIC
2012, across six solver models (GLM-5, Kimi-K2.5, Qwen3.5-plus, MiniMax-M2.5,
Claude Opus 4.6, Claude Haiku 4.5). Reported logistics five-model average
action accuracy: 70.3% zero-shot baseline, 73.3% few-shot, 69.2% unrefined
rules, 78.9% after EISR refinement, and 79.6% when the same rule content is
compiled to executable Python rather than interpreted by an LLM at inference
time; an LLM-automated refinement cycle reportedly matches a human-expert
refinement cycle in accuracy at a small fraction of the cost. Its paper
explicitly distinguishes its approach from DSPy-style parametric prompt
chains, framing the optimized artifact as "an externalized, human-readable
rule document amenable to compliance audit and version control" - a framing
that pre-figures treating prompts as governed software artifacts. Its
regression gate and best-snapshot rollback operate at the whole-document
level, not per section, and its stated modularity lives in error clustering
rather than in prompt structure.

**A documented replication concern.** The paper's own Appendix states that one
round was diagnosed "from v1's iter-30 errors plus Opus v1's heldout errors" -
meaning the nominally held-out evaluation set was inspected by a human curator
while writing refinement rules for the public LegalBench probe specifically
(the paper's separate, primary damage-audit study is explicit that its held-out
sets stay disjoint from the refinement pool). This repository replicated the
protocol and separately ran a deliberate oracle/leak diagnostic (mining
directly from the sealed 64-item test pool) and found that an automated,
two-round, sub-$0.20 rewrite can match or exceed the reported human-curated
gain under the same test exposure - evidence that a meaningful share of a
reported gain on that specific public benchmark is explainable by test
exposure rather than by the refinement mechanism itself. This is a concrete,
citable caution about reusing that benchmark's published numbers uncritically,
not a claim that Trace2Policy's core mechanism (clustered errors, regression
gate, best-snapshot rollback) is invalid - those are real and worth adopting.

### 9.2 What FDPO should adopt from Trace2Policy

| Strength | How it maps onto FDPO |
|---|---|
| Regression gate with a fixed drop threshold | A real deployment gate, distinct from the current permissive `accept_margin=1.0` validation-selection default used for scientific observation |
| Best-snapshot fallback after stagnation | Already present in FDPO's registry machinery; should be reused for a stricter deployment variant |
| MISSING / WRONG / CONFLICT error taxonomy | A candidate structured label set for the failure traces shown to the optimizer, worth an ablation |
| Compiled-execution comparison | Orthogonal, but worth citing: for tasks where the "prompt" reduces to enumerable rules, a compiled non-LLM execution path can beat LLM-interpreted execution |
| Explicit "rule document as an audited software artifact" framing | Directly reusable framing for the SANER submission (Section 16) |

### 9.3 ETGPO and APEX (adjacent, offline)

**ETGPO** (Section 4.3) and **APEX** (Wang et al., 2026, arXiv:2606.11459,
Google Research) both push toward smarter offline data use rather than online
operation: APEX classifies training examples by optimization lineage into
Easy/Hard/Mixed tiers and concentrates mutation and ranking budget on the
"Mixed" tier (examples some candidates solve and others do not), reporting
gains of 11.2% on Gemini 2.5 Flash and 6.8% on Gemma 3 27B under a fixed
5,000-evaluation-call budget. Both remain single-shot offline optimizers over
a labeled dataset; neither operates on live production signals.

---

## 10. Feedback and human-signal family

### 10.1 PromptWizard (Agarwal, Magazine, Singh, Dani, Ganu, Nambi, Microsoft Research India, Findings of ACL 2025, arXiv:2405.18369)

PromptWizard is a self-evolving, feedback-driven framework that jointly
optimizes instructions and in-context examples through five recurring
components: mutate candidate instructions using predefined "thinking styles,"
score them on a small minibatch, critique the best-scoring candidate against
its failures, synthesize an improved instruction from that critique, and
separately select and synthesize few-shot examples (including generating new
synthetic examples), finally adding a chain-of-thought reasoning pass and a
task-intent/expert-persona pass. Evaluated on 45 tasks (19 BIG-Bench
Instruction Induction, 23 BIG-Bench Hard, 3 arithmetic-reasoning datasets)
with GPT-3.5-Turbo and GPT-4 as base models and a Llama-70B prompt-generation
ablation, it reports outperforming Instinct, InstructZero, APE, PromptBreeder,
and EvoPrompt on BBH (88.1 versus EvoPrompt's 75.03 and APE's 71.85), strong
GSM8K accuracy (90.0), and winning or tying on 13 of 19 BBII tasks zero-shot
and 16 of 19 one-shot, while using far fewer total LLM calls than InstructZero,
PromptBreeder, or EvoPrompt in its own cost accounting. It is the strongest
prior demonstration that showing an optimizer both failed and successful
examples, rather than a scalar score, produces better and more efficient
optimization - directly supporting FDPO's design choice, and directly
undercutting any claim that showing failures to the optimizer is itself novel.
Its own reported cost accounting (a 69-call total for BBII) is derived using
three sequential refinement iterations while its hyperparameter table lists a
default of five, an internal inconsistency worth noting rather than
propagating.

### 10.2 Self-Refine, GATE, PLHF, APOHF

**Self-Refine** (Madaan et al., NeurIPS 2023, arXiv:2303.17651) has a single
LLM generate an output, critique its own output, and refine it, repeated for a
few iterations; no prompt template is ever updated, only the output, which
makes it a self-critique inference-time technique rather than a prompt
optimizer proper. **GATE** (Joko et al., 2024) uses Likert-scale human ratings
of (prompt, output) pairs to drive a rewriter LLM; the collection burden scales
with the number of optimization rounds. **PLHF** formalizes prompt
optimization as Bayesian optimization over a learned human-preference
surrogate: humans rate 50-200 (input, output) pairs, a surrogate model learns
to predict preference, and a black-box optimizer maximizes predicted
preference, requiring surrogate training and heavy upfront labeling. **APOHF**
(Lin et al., NeurIPS 2024, arXiv:2405.17346) treats prompt optimization as a
dueling-bandit problem: at each round the optimizer proposes two candidates, a
human indicates a preference, and a Bayesian belief over the prompt space is
updated (for example via Double Thompson Sampling) until the highest-preference
arm is returned.

| Method | Feedback source | Requires surrogate/training? | Update target |
|---|---|---|---|
| Self-Refine | LLM self-critique | No | Output only, not the prompt |
| GATE | Human Likert ratings | No (direct rewrite) | Prompt |
| PLHF | Human preference pairs | Yes, a surrogate preference model | Prompt |
| APOHF | Human pairwise preference (dueling bandit) | Belief update, no separate trained model | Prompt |
| PromptWizard | LLM critique + selected pos/neg examples | No | Instruction + examples |

### 10.3 Evaluation-instructed optimization ("Knowing How to Edit")

A closely related 2025 line of work (arXiv:2511.19829 per this repository's
prior notes) proposes unifying evaluation and optimization: a small,
execution-free evaluator model predicts prompt quality directly from text
(avoiding a full LLM rollout per candidate) and produces structured critique
that tells the optimizer exactly which aspect to fix, tested on BBH, GPQA
Diamond, and LegalBench definition classification as seen tasks and on MATH500
and MedQA as fully held-out generalization tasks. It solves the cost of
*evaluating* many candidates; FDPO's contribution is orthogonal - reducing how
much labeled data and how many candidates are needed in the first place by
extracting maximal signal from one round of raw failures.

---

## 11. The 2025 optimization-perspective survey (taxonomy cross-reference)

**"A Survey of Automatic Prompt Engineering: An Optimization Perspective"**
(Li, Wang, Li, Jin, arXiv:2502.11560v1, 2025) is a taxonomy paper, not a new
optimizer, and it predates GEPA, MPO, aPSF, and Trace2Policy. Its formal
contribution is casting prompt optimization as maximizing an expected
performance metric over discrete, continuous, or hybrid prompt spaces, and
organizing methods along optimization variables (instructions, thoughts,
few-shot exemplars, and, for vision-language models, spatial annotations, plus
continuous soft-prompt embeddings) and four optimization-method paradigms:
FM-based optimization (heuristic meta-prompts, automatic meta-prompt
generation, strategic search/replanning - this is where ProTeGi, APE, OPRO,
and PromptWizard live in its own categorization table), evolutionary computing
(EvoPrompt, PromptBreeder), gradient-based optimization (soft-prompt tuning,
discrete-token gradient methods), and reinforcement learning (prompt editing
as RL actions, multi-objective/inverse RL). Its stated open frontiers -
constrained optimization (semantic/ethical constraints on edits), multi-task
optimization (negative transfer across tasks), **online prompt optimization**,
multi-objective optimization (Pareto-based trade-offs), heterogeneous-modality
optimization, bi-level optimization for reasoning-chain-driven models, and
**agent-oriented prompt design** - are exactly the frontiers this repository's
work sits in. This survey establishes that FDPO is discrete instruction
optimization by its own taxonomy (moving to hybrid instruction/exemplar
optimization only if example selection is added), and that failure-driven
meta-prompting is already a recognized category rather than a novel one; it
provides no empirical evidence for ranking algorithms and cannot be used to
validate any specific method's claims.

---

## 12. Consolidated capability and rigor matrix

This single table replaces the three overlapping capability tables previously
scattered across `literature_survey.md`, `related_works.md`, and
`prompt_optimization_literature_study.md`.

| Method | Family | Sees raw failed output | Protects prior successes | Regression gate (veto) | Modular/structured prompt | Online | Solver models tested | Seeds/stat. rigor reported |
|---|---|---|---|---|---|---|---|---|
| APE | Foundational | No | No | No | No | No | 1-2 | No |
| ProTeGi | Gradient-inspired | Yes | No | Beam-search selection only | No | No | 1 | 3 runs |
| TextGrad | Gradient-inspired | Yes (graph traces) | Validation reversion | Yes (graph-node level) | Node-level | No | 2 | No |
| EvoPrompt | Evolutionary | **No** | Population fitness only | No | No | No | 2 | 3 seeds (Alpaca), 1 (GPT-3.5) |
| PromptBreeder | Evolutionary | No | Tournament selection | No | No | No | 1 | Not reported |
| GEPA | Evolutionary + reflective | Yes (full traces + feedback) | Pareto validation | Minibatch/Pareto selection | Module-level in compound systems | No | 2 | Not clearly stated |
| PromptAgent | Search (MCTS) | Yes | UCT back-propagation | No | No | No | 2 | Not reported |
| OPRO | LLM-as-optimizer | No | No | No | No | No | up to 5 | Convergence-step analysis only |
| MIPROv2 (DSPy) | Framework | No (score-driven proposal) | Validation selection | No | Predictor-level | No | 3 | Not consistently reported |
| SAMMO | Modular | Partial | No | No | Component tree | No | Several | Not reported |
| MPO | Modular | **No** | No | **No** | Fixed 5 sections | No | 2 | **No** |
| aPSF | Modular | Yes | No | No | Auto-discovered | No | Several | Not reported |
| Trace2Policy/EISR | Regression-safe | Yes (clustered) | Whole-document regression gate | **Yes** | Flat rule doc, not sectioned | Partial (flywheel trigger) | 6 | Reports across models, but the public LegalBench probe has a documented test-exposure caveat |
| PromptWizard | Feedback | Yes | Yes (positive examples) | No explicit gate | No | No | 2 base + 1 generation-only | 3-run averages |
| APOHF | Human feedback | N/A (human preference, not correctness) | No | No | No | Bandit updates online | N/A | Not comparable |
| FDPO (current) | LLM-as-optimizer, failure-driven | **Yes** (question + wrong output + reference) | Random correct examples shown | **Default off** (`accept_margin=1.0` ships almost anything); optional strict mode exists | Fixed 5 sections (markdown) | No | 1 solver family thoroughly (gpt-4o-mini) + 1 confirmatory run (Claude Haiku 4.5) | Mixed: 3 seeds in older runs, 2 in newer, 1 in the newest cross-model replication |

The single most citable, falsifiable positioning line this table supports:
**no published method combines (a) modular/section-decomposed prompts, (b) a
real veto-capable regression gate, (c) raw-failure-conditioned rewriting, and
(d) reported per-item recovery/regression churn.** FDPO has (a), (c), and a
first-class measurement of (d); it does not yet have a real (b) by default.
Trace2Policy has (b) and partial (d)-adjacent clustering but not (a). MPO has
(a) only. This is the gap statement, tightened to what current evidence
actually supports (see Section 15).

---

## 13. Dataset reference (consolidated)

| Dataset | Domain | Typical split | Task format | Standard metric | Used by |
|---|---|---|---|---|---|
| GSM8K | Grade-school math reasoning | 7,473 train / 1,319 test | Free-text multi-step | Exact match | APE, OPRO, TextGrad, PromptBreeder, MIPROv2, FDPO |
| BBH (23 subtasks) | Multi-step logic | ~100-250 train / 200-250 test per task | Mixed multiple-choice/generation | Accuracy | APE, OPRO, PromptAgent, EvoPrompt, GEPA, PromptWizard |
| MMLU | General academic knowledge | Large; commonly 6-subject subsample | Multiple-choice (A-D) | Accuracy | TextGrad, MPO, DSPy, FDPO |
| ARC-Challenge | Science reasoning | 1,119 train / 1,172 test (official) | Multiple-choice (A-D) | Accuracy | MPO, FDPO |
| Instruction Induction / BBII | Instruction discovery | 10 demos / 50 test per task | Varies | Accuracy, BERTScore-F1 | APE, PromptWizard, survey taxonomy |
| StrategyQA | Commonsense reasoning | 2,290 / 490 | Binary | Accuracy | APE, OPRO, GLaPE |
| AQuA-RAT | Algebraic word problems | 97,467 / 254 | Multiple-choice + rationale | Accuracy | OPRO, PE2, PromptWizard |
| LegalBench Hearsay | Legal rule application | ~99 total examples (small) | Binary (Yes/No) | Accuracy, macro-F1 | Trace2Policy, FDPO |
| LegalBench Contract NLI | Legal clause classification | Task-defined | Binary | Accuracy | Trace2Policy, FDPO (planned) |
| LegalBench (broader, 162 tasks) | Legal reasoning | ~500 avg per task | Mixed | Accuracy | "Knowing How to Edit," DSPy MIPROv2 |
| MedQA | Medical licensing exam | 10,178 / 1,273 | Multiple-choice | Accuracy | MIPROv2, "Knowing How to Edit" (generalization) |
| GPQA Diamond | Graduate-level science QA | ~198 / ~50 | Multiple-choice | Accuracy | TextGrad, ETGPO, "Knowing How to Edit" |
| HumanEval | Code generation | 0 / 164 | Python function | Pass@1 | TextGrad, FIPO |
| MATH500 | Competition mathematics | 500 (held out) | Free text | Exact match | "Knowing How to Edit" (generalization) |
| Ethos / Liar / Sarcasm / Jailbreak | Safety/moderation classification | Task-specific, hundreds to low thousands | Binary/F1 | F1 or accuracy | ProTeGi |
| SST-2 / SST-5 / AG's News / Subj / CR / MR / TREC | Sentiment/topic/subjectivity classification | Standard splits | Classification | Accuracy | EvoPrompt |
| SAMSum / ASSET | Summarization / simplification | Standard splits | Generation | ROUGE-L / SARI | EvoPrompt |
| HotpotQA | Multi-hop QA | 90,447 / 7,405 | Free text | EM + F1 | DSPy, GEPA |
| IFBench / IFEval | Instruction-following constraints | Official | Constraint satisfaction | Constraint pass rate | GEPA; **not yet used by FDPO** (recommended addition) |
| Logistics audit (proprietary) | Compliance/operations decisions | 3,349 cases over 22 days | Action classification | Action accuracy | Trace2Policy |
| BPIC 2012 | Business-process event log | Standard | Process/event classification | Task-specific | Trace2Policy |

---

## 14. Evaluation protocols and reproducibility conventions

Conventions that recur across the strongest papers in this review, useful as
a checklist when designing FDPO's own experiment matrix (cross-referenced,
not duplicated, in the finish plan document's statistical section):

- **Dual-LLM discipline.** Separate the model proposing rewrites from the
  model executing them; run the executor at temperature 0 and the proposer at
  a higher temperature for diversity (ProTeGi, TextGrad, OPRO, PromptAgent,
  PE2, GEPA all follow this).
- **Untouched test set.** MIPROv2's 90/10 train/validation convention, with
  the test partition never used for any selection decision, is the strictest
  and most citable convention to imitate.
- **Multiple seeds with dispersion reported.** Field convention is a minimum
  of 3 seeds with mean and spread reported; several of the strongest papers
  reviewed here (EvoPrompt's GPT-3.5 condition, OPRO, MPO, PromptAgent) fall
  short of this on at least one experimental arm, which is a citable gap to
  exploit rather than repeat.
- **Budget-normalized comparison.** Report accuracy against a fixed evaluation
  or rollout budget (APEX's fixed 5,000-call budget; GEPA's rollout-vs-score
  curves) rather than only a final accuracy number, since search-heavy
  methods (EvoPrompt, GEPA, MIPROv2 heavy mode) can trivially buy accuracy
  with more calls.
- **LLM-as-judge validation.** When ground truth is unavailable, validate the
  judge against roughly 100-200 human annotations and require a Cohen's kappa
  of at least 0.7 before trusting the judge as the sole evaluator.
- **Ablation minimums.** At least one ablation removing the failure-example
  signal, one removing the protected-success signal, and one on
  threshold/budget sensitivity, per the pattern DSPy, ProTeGi, and MPO's own
  self-critique (its future-work section) all call for.

---

## 15. The literature gap and an honest positioning of FDPO

**One-sentence gap statement, tightened to current evidence:** no published
method combines (a) an explicit, section-decomposed prompt representation,
(b) a real veto-capable regression gate applied by default (not merely a
validation-based *selection* rule), (c) raw-failure-conditioned single-pass
rewriting, and (d) first-class reporting of per-item recovery/regression churn
alongside aggregate accuracy. MPO has (a) only. aPSF has (a) plus a partial
version of failure-aware routing. Trace2Policy has (b) and a form of clustered
error signal, but is not modular and its public benchmark numbers carry a
documented test-exposure caveat. PromptWizard and GEPA both have strong
failure/trace-conditioned rewriting but neither reports (d) as a first-class
metric, and neither is built around a simple, auditable five-section
markdown artifact.

**What current evidence supports claiming (cross-referenced from the finish
plan document's Section 9, restated here for a single point of truth):**

1. A small number of whole-prompt reflective updates, conditioned on raw
   solver failures and a sample of protected successes, measurably change
   behavior on selected task regimes without any weight update.
2. Aggregate accuracy hides a substantial, reproducible recovery-regression
   trade-off; per-item churn should be reported as a first-class result, not
   an ablation footnote.
3. Task type (reasoning-heavy versus recall-heavy) and baseline headroom
   predict the sign of the result more reliably than the optimizer model
   choice does.
4. A single or few-call reflective rewrite can be dramatically cheaper than
   population or Pareto search at comparable or better quality, once
   cost-matched.

**What current evidence does not yet support, and should not be claimed
until the finish-plan's Phase B/C experiments are run:** that the algorithm is
finished, that it is model-general from one solver family, that its default
gate prevents regression (it currently ships almost anything under
`accept_margin=1.0`), that it discovered chain-of-thought independently of its
own typed meta-prompt hint, or that it is production-ready self-healing.

---

## 16. Fit to SANER 2027 (Agentic AI4SE Track)

**Venue facts.** SANER 2027 is the 34th IEEE International Conference on
Software Analysis, Evolution, and Reengineering, held 9-12 March 2027 in
Richmond, Virginia. The Agentic AI4SE Track (co-chaired by Yiling Lou and
Xiwei Xuan) solicits work on agentic AI systems for software engineering, with
particular emphasis on software analysis, evolution, maintenance, and
reengineering, and explicitly on agents studied as software-engineering
systems - reasoning over artifacts, maintaining state, invoking tools,
coordinating with humans or other agents, and operating under constraints such
as correctness, cost, safety, privacy, and maintainability, rather than as
isolated model calls.

**Logistics.** Abstract submission is mandatory (19 Oct 2026), full paper
deadline 23 Oct 2026, notifications 8 Dec 2026, camera-ready and author
registration both due 8 Jan 2027 (all AoE). Submissions are limited to 10 pages
plus up to 2 additional reference-only pages, IEEE conference format
(`\documentclass[10pt,conference]{IEEEtran}`, no `compsoc` option), and must
follow IEEE's policy on generative-AI-tool use. **Review is double-anonymous**:
no author names or affiliations, self-citations written in third person,
acknowledgments omitted, and any linked code/data/tools anonymized. Papers are
scored on relevance, originality/novelty, significance, soundness, evaluation
quality, open science/verifiability, and presentation.

**Topic-of-interest mapping for this work:**

| Track topic (paraphrased) | How this work maps |
|---|---|
| Feedback, execution, and tool-use mechanisms for AI agents working with software artifacts | FDPO's core mechanism - raw failure traces plus protected successes driving a single reflective rewrite - is exactly this class of feedback mechanism, generalized to any artifact an agent produces, not only natural-language answers |
| Benchmarking and evaluation of agentic AI4SE systems: task design, metrics, reproducibility, reliability, cost | The churn decomposition (recovery rate, regression risk, McNemar/bootstrap testing, no-change control) from the finish plan is a direct, exportable evaluation-methodology contribution |
| Safety, security, privacy, accountability, and governance for agents that modify, execute, or deploy software | The regression-gate-versus-observation distinction, canary/rollback lifecycle, and PII/poisoning concerns in the finish plan's production section speak directly to this topic |
| Software engineering *for* agentic AI systems: requirements, architecture, testing, monitoring, maintenance, evolution of agent-based software systems | The strongest possible framing: prompts as versioned software artifacts requiring regression testing, canary rollout, and rollback, exactly mirroring standard software release engineering |
| Industrial experiences, case studies, and lessons learned from deploying agentic AI4SE systems | Achievable if the neutral trace-event contract and one LangChain/OpenAI-Agents adapter from the finish plan's Phase D are implemented and demonstrated before submission |

**Critical fit gap to close before submission.** Every dataset evaluated so
far (GSM8K, ARC-Challenge, MMLU, LegalBench) is a general NLP/QA benchmark,
not a software-engineering artifact. SANER's Agentic AI4SE track is explicitly
scoped to software analysis, evolution, maintenance, and reengineering, and to
agents that reason over software artifacts. Submitting with only NLP/QA
benchmarks risks a low "Relevance" score even if the mechanism and evaluation
rigor are excellent. **Recommendation:** add at least one genuine
software-engineering case study evaluated with the same churn methodology,
for example an LLM-based code-review-comment agent, a bug-triage or
bug-localization agent, a commit-message-quality agent, or a test-repair
suggestion agent, and evaluate FDPO's failure-conditioned rewrite against a
score-only baseline on that task using the same recovery/regression reporting
as the rest of the paper. This also directly unlocks the strongest topic
match above (prompts-as-software-artifacts with regression testing and
rollback) rather than framing the paper as general prompt engineering with an
SE-adjacent example.

**Recommended paper framing for this venue specifically:**

> Treat an LLM prompt as a versioned software artifact. Apply standard
> software-engineering discipline - regression testing against a held
> correct-behavior suite, canary rollout, and rollback - to prompt updates
> proposed from an agent's own observed failures, and report the update's
> effect with the same rigor a code change would require (recovery rate,
> regression risk, and a no-change statistical control), rather than a single
> aggregate accuracy delta.

This framing satisfies "software engineering for agentic AI systems" as a
primary topic, "benchmarking and evaluation" as a secondary topic through the
churn methodology, and "safety/governance" through the gate/canary/rollback
lifecycle, while still allowing the NLP/legal/math results to serve as
controlled mechanism studies rather than the paper's sole evidence.

---

## 17. Drafting aid: related-work paragraph templates

These are written in the third person and contain no self-identifying
language, ready to adapt for a double-anonymous submission. Replace bracketed
placeholders; do not present them as final prose without checking the exact
numbers against Sections 3-11 above and the finish-plan's result ledger.

**Paragraph - gradient-inspired / failure-driven family:**

> Feedback-driven prompt refinement was introduced by textual-gradient methods
> such as ProTeGi [cite], which critique a prompt from observed failures and
> select rewrites via beam search, and later generalized into a full
> computation-graph formulation by TextGrad [cite]. PromptWizard [cite]
> extends this line by jointly optimizing instructions and in-context
> examples from both failed and successful cases, and GEPA [cite] further
> conditions reflective mutation on full execution traces and evaluator
> feedback with Pareto-based candidate retention. The present work differs
> from this family in [restricting itself to a single reflective update by
> default / reporting per-item recovery and regression churn as a first-class
> result / evaluating a simpler, auditable five-section prompt
> representation], rather than in the use of raw failures itself, which this
> family already establishes as effective.

**Paragraph - evolutionary family:**

> Evolutionary approaches such as EvoPrompt [cite] and PromptBreeder [cite]
> search a population of prompts using LLM-implemented mutation and crossover
> operators guided by a scalar development-set fitness score, without
> exposing the proposer to individual failed examples. This work instead
> conditions each update directly on the solver's own wrong outputs and a
> matched set of protected successes, trading population-scale search breadth
> for per-update evidence density; Section [X] reports a controlled comparison
> between the two information regimes at matched rollout budget.

**Paragraph - modular / structure-aware family:**

> Modular prompt optimization decomposes a prompt into labeled components and
> updates them individually, as in SAMMO's tagged component tree [cite], MPO's
> fixed five-section schema [cite], and aPSF's auto-discovered factorization
> [cite]. None of these methods exposes the optimizer to the solver's raw
> failed outputs, and none applies a regression gate that can veto a
> candidate before it is shipped. This work adopts a comparable fixed
> five-section representation but conditions its single rewrite directly on
> raw failure traces and reports the resulting per-item churn explicitly.

**Paragraph - regression-safe / production family:**

> Closest to a production deployment concern, Trace2Policy [cite] refines a
> flat, human-readable rule document from clustered errors under an explicit
> regression gate and best-snapshot rollback, evaluated across six solver
> models on a proprietary operational stream and public legal-reasoning
> benchmarks. Unlike Trace2Policy, this work operates over a structured,
> section-decomposed prompt rather than a flat rule list, and treats the
> gate/rollback lifecycle as a deployment-time safety mechanism kept
> deliberately separate from the observational, always-logged scientific
> measurement of a candidate's effect.

**Paragraph - taxonomy positioning:**

> Following the optimization-theoretic taxonomy of automated prompt
> engineering [cite survey], this work is a discrete, FM-based, failure-driven
> prompt optimizer; it does not optimize continuous embeddings and does not
> currently treat few-shot exemplars as an optimized variable, though doing so
> would place it in the hybrid instruction/exemplar category alongside
> PromptWizard and PromptBreeder.

---

## 18. Master reference list

| # | Method | Authors (as available) | Venue/date | Identifier |
|---|---|---|---|---|
| 1 | AutoPrompt | Shin et al. | EMNLP 2020 | arXiv:2010.15980 |
| 2 | Chain-of-Thought prompting | Wei et al. | NeurIPS 2022 | n/a |
| 3 | Zero-shot Chain-of-Thought | Kojima et al. | NeurIPS 2022 | n/a |
| 4 | Auto-CoT | Zhang et al. | ICLR 2023 | n/a |
| 5 | APE | Zhou et al. | ICLR 2023 | arXiv:2211.01910 |
| 6 | ProTeGi | Pryzant et al. | EMNLP 2023 | arXiv:2305.03495 |
| 7 | TextGrad | Yuksekgonul et al. | 2024 | arXiv:2406.07496 |
| 8 | GLaPE | Zhang et al. | 2024 | n/a |
| 9 | AutoHint | Sun et al. | 2023 | n/a |
| 10 | CRISPO | He et al. | 2025 | n/a |
| 11 | ETGPO | (unspecified) | 2026 | arXiv:2602.00997 |
| 12 | EvoPrompt | Guo et al. | ICLR 2024 | arXiv:2309.08532 |
| 13 | PromptBreeder | Fernando et al. | 2023 (DeepMind) | arXiv:2309.16797 |
| 14 | GEPA | Agrawal et al. | ICLR 2026 | (arXiv id not confirmed in reviewed materials) |
| 15 | PromptAgent | Wang et al. | ICLR 2024 | arXiv:2310.16427 |
| 16 | OPRO | Yang et al. | ICLR 2024 | arXiv:2309.03409 |
| 17 | PE2 | Ye et al. | NAACL 2024 | arXiv:2311.05661 |
| 18 | PRewrite | Kong et al. | 2024 | arXiv:2401.08189 |
| 19 | BPO | Cheng et al. | 2024 | arXiv:2311.04155 |
| 20 | FIPO | Lu et al. | 2024 | n/a |
| 21 | StablePrompt | (unspecified) | 2024 | n/a |
| 22 | DSPy | Khattab et al. | ICLR 2024 | arXiv:2310.03714 |
| 23 | MIPROv2 | Opsahl-Ong et al. | 2024 | arXiv:2406.11695 |
| 24 | SIMBA | DSPy team | 2025 | n/a |
| 25 | SAMMO | Schnabel and Neville | EMNLP 2024 Findings | arXiv:2404.02319 |
| 26 | MPO | Sharma and Henley | Jan 2026 (CMU) | arXiv:2601.04055 |
| 27 | aPSF | Liu et al. | Apr 2026 | arXiv:2604.06699 |
| 28 | Trace2Policy / EISR | Zha, Wang, Zhou, Song | Jun 2026 (SF Express) | arXiv:2606.10457 |
| 29 | APEX | Wang et al. | 2026 (Google Research) | arXiv:2606.11459 |
| 30 | PromptWizard | Agarwal, Magazine, Singh, Dani, Ganu, Nambi | Findings of ACL 2025 (Microsoft Research India) | arXiv:2405.18369 |
| 31 | Self-Refine | Madaan et al. | NeurIPS 2023 | arXiv:2303.17651 |
| 32 | GATE | Joko et al. | 2024 | n/a |
| 33 | PLHF | (unspecified) | ~2024 | n/a |
| 34 | APOHF | Lin et al. | NeurIPS 2024 | arXiv:2405.17346 |
| 35 | "Knowing How to Edit" (evaluation-instructed optimization) | (unspecified) | 2025 | arXiv:2511.19829 |
| 36 | Automatic Prompt Engineering survey | Li, Wang, Li, Jin | 2025 | arXiv:2502.11560v1 |

Entries marked "unspecified" or with no confirmed identifier were captured
from this repository's own prior research notes without an independently
re-verified primary source in this session; re-verify before citing in a
submitted paper.

---

## 19. Maintenance note

When a new method is reviewed, add it to the relevant family section above
(Sections 3-11), add one row to the consolidated matrix (Section 12), one row
to the dataset table if it introduces a new benchmark (Section 13), and one
row to the master reference list (Section 18). Do not create a fourth
parallel literature document; extend this one.

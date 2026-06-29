# Literature Survey: Prompt Optimization for Large Language Models

**A Case Study of Automatic Prompt Optimization Methods, 2020–2026**
**Coverage:** 30+ methods, 18 datasets, 4 method families, 9 tables
**Last revised:** June 2026

---

## Abstract

Prompt optimization has evolved from a craft-driven engineering practice into a
quantitative research field with measurable benchmarks, reproducible protocols,
and a growing taxonomy of methods. This survey reviews automatic prompt
optimization (APO) techniques developed between 2020 and 2026, organized by the
optimization mechanism each method employs: discrete search, gradient-inspired
text differentiation, evolutionary search, large language models acting as
optimizers, framework-level pipelines, feedback-driven systems, and data-aware
variants. Each method is described in terms of its core algorithm, experimental
setup, dataset coverage, and reported results. Particular attention is given to
the *LLM-as-optimizer* family, which has produced the largest number of recent
methods and is the dominant mechanism in current production-oriented systems.
Comparison tables are provided within and across families, and the closing
sections catalogue the datasets, metrics, and evaluation protocols that recur
across the literature.

---

## Table of Contents

1. [Introduction and Taxonomy](#1-introduction-and-taxonomy)
2. [Foundational Works](#2-foundational-works)
3. [Gradient-Inspired Methods](#3-gradient-inspired-methods)
4. [Evolutionary and Search-Based Methods](#4-evolutionary-and-search-based-methods)
5. [LLM-as-Optimizer Methods](#5-llm-as-optimizer-methods)
6. [Framework-Level Optimizers](#6-framework-level-optimizers)
7. [Feedback and Human-Signal Methods](#7-feedback-and-human-signal-methods)
8. [Data-Aware and Runtime-Adjacent Methods](#8-data-aware-and-runtime-adjacent-methods)
9. [Evaluation-Focused Methods](#9-evaluation-focused-methods)
10. [Datasets Reference](#10-datasets-reference)
11. [Evaluation Protocols](#11-evaluation-protocols)
12. [Cross-Cutting Summary](#12-cross-cutting-summary)

---

## 1. Introduction and Taxonomy

### 1.1 Scope

Automatic prompt optimization (APO) refers to algorithms that search, refine,
or generate natural-language instructions for large language models without
manual engineering. The field has grown rapidly since 2022, with methods now
spanning gradient-style approaches, evolutionary algorithms, LLM-driven
meta-optimization, and full programming frameworks. This survey covers
approximately thirty methods published between 2020 and 2026, focusing on the
algorithm, experimental setup, and reported empirical results in each case.

### 1.2 Taxonomic Axes

Three orthogonal axes organize the literature throughout this survey.

**Axis A — When optimization occurs:**

- *Offline* — optimization runs once on a fixed labeled dataset before
  deployment. Almost all published methods fall here.
- *Online* — optimization runs continuously during deployment using live
  signals. A small but growing number of recent methods explore this setting.

**Axis B — What signal drives the optimizer:**

- *Task accuracy* against gold labels (most common).
- *LLM-generated critique text*, used as a gradient analogue.
- *Human feedback* — preferences, ratings, or free-text comments.
- *Multi-objective combinations* — accuracy plus cost, faithfulness, or
  formatting.

**Axis C — Optimization mechanism:**

- *Discrete search* — enumeration, beam search, MCTS.
- *Gradient-inspired* — textual gradients, computation-graph backpropagation.
- *Evolutionary* — mutation, crossover, Pareto retention.
- *Bayesian / model-based* — Optuna, TPE samplers, preference surrogates.
- *LLM-as-optimizer* — a separate LLM proposes new prompts conditioned on
  trajectory history.
- *Fine-tuning-based* — a small model is trained to act as the optimizer
  itself.

### Table 1.1 — Taxonomy Summary

| Axis | Values | Distribution in current literature |
|---|---|---|
| When | Offline / Online | ~95% offline, ~5% online |
| Signal | Accuracy / Critique / Human / Multi-objective | Accuracy dominant; critique-driven growing |
| Mechanism | Search / Gradient / Evolutionary / Bayesian / LLM-as-optimizer / Fine-tuning | LLM-as-optimizer dominant in 2024–2026 |

### 1.3 Reading Guide

Sections 2 through 9 are organized by method family, with the LLM-as-optimizer
family (Section 5) covered in greatest depth because it has produced the largest
number of recent methods and is the dominant mechanism in current
production-oriented systems. Each section ends with a comparison table
summarizing the methods in that family. Sections 10 and 11 collect dataset and
evaluation conventions; Section 12 provides cross-cutting summary tables.

---

## 2. Foundational Works

### 2.1 AutoPrompt

**Citation:** Shin et al., 2020 | EMNLP 2020 | arXiv:2010.15980

AutoPrompt is one of the earliest automatic prompt construction methods. Given
a labeled training set, it uses gradient-based search over the vocabulary to
find discrete trigger tokens that, when appended to inputs, maximize the
model's probability of producing the correct label. The approach is restricted
to small language models with accessible gradients, but established the
formulation of prompt construction as a discrete optimization problem.

**Core mechanism:** at each step, compute the gradient of the loss with respect
to the embedding of a placeholder trigger token; replace the token with the
vocabulary item whose embedding aligns most with the gradient (a HotFlip-style
update). Repeat across multiple trigger positions for a fixed number of steps.

**Reported settings:** sentiment classification, NLI, fact retrieval, and
relation extraction on RoBERTa-base/large. No human-readable instructions are
produced — outputs are short token sequences.

### 2.2 Chain-of-Thought Prompting

**Citation:** Wei et al., 2022 | NeurIPS 2022

Although not an optimizer, chain-of-thought (CoT) prompting is the most
frequently cited baseline in subsequent APO papers. CoT introduces reasoning
demonstrations into the prompt — typically 8 hand-crafted
question–rationale–answer triples — and measures the resulting improvement on
multi-step arithmetic and commonsense reasoning benchmarks. Reported gains on
GSM8K, MultiArith, AQuA, and StrategyQA established the importance of
intermediate reasoning steps for large models.

### 2.3 Zero-Shot Chain-of-Thought

**Citation:** Kojima et al., 2022 | NeurIPS 2022

The zero-shot CoT variant replaces hand-crafted demonstrations with the single
trigger phrase *"Let's think step by step."* Despite its simplicity, this
baseline produces substantial improvements over direct answering on the same
benchmarks used in Wei et al. (2022). Most APO methods report this trigger as
either the initial prompt or the primary baseline.

### 2.4 Auto-CoT

**Citation:** Zhang et al., 2022 | ICLR 2023

Auto-CoT automates the construction of CoT demonstrations. Questions in the
training set are clustered (typically by Sentence-BERT embeddings), one
representative is sampled per cluster, and zero-shot CoT is applied to that
representative to produce a demonstration. The resulting demonstrations are
concatenated as a few-shot prompt. The method removed the manual cost of
crafting reasoning chains while matching the accuracy of human-engineered
few-shot CoT.

### 2.5 APE — Automatic Prompt Engineer

**Citation:** Zhou et al., 2022 | ICLR 2023 | arXiv:2211.01910

APE frames prompt generation as a black-box optimization problem. An LLM is
shown a small set of input–output demonstrations and asked to generate
candidate instructions consistent with them. Candidates are scored on a
held-out validation set; the top candidates are paraphrased to generate a
second-generation pool; the best surviving candidate is returned.

**Core procedure:**

1. Show the LLM 10 input–output pairs in either a forward template
   (*input → output*) or backward template (*output → input*).
2. Generate $N$ candidate instructions from the LLM (typically $N = 250$).
3. Score each candidate by accuracy or log-probability on a validation set of
   50 examples.
4. Paraphrase the top-$K$ candidates using an iterative refinement loop.
5. Return the highest-scoring final instruction.

**Datasets used:** Instruction Induction benchmark (24 tasks), BIG-Bench
Instruction Induction (21 tasks), and GSM8K for CoT discovery (using ~3.5% of
the 7,473-example training split = ~261 examples; full 1,319-example test set).

**Models used:** text-davinci-001 and text-davinci-002 as both generator and
scorer.

**Notable empirical finding:** APE rediscovered a stronger CoT trigger than
"Let's think step by step." for GSM8K — namely *"Let's work this out in a step
by step way to be sure we have the right answer."* — improving zero-shot CoT
accuracy by 2.3 absolute points.

### Table 2.1 — Foundational Methods

| Method | Year | Mechanism | Output type | Models tested |
|---|---|---|---|---|
| AutoPrompt | 2020 | Discrete gradient search | Trigger tokens | RoBERTa-base/large |
| CoT | 2022 | Manual demonstrations | Few-shot prompt | PaLM, GPT-3 |
| Zero-shot CoT | 2022 | Single trigger phrase | Zero-shot prompt | text-davinci-002, PaLM |
| Auto-CoT | 2022 | Cluster + sample | Few-shot prompt | text-davinci-002 |
| APE | 2022 | LLM generation + score | Instruction | text-davinci-001/002 |

---

## 3. Gradient-Inspired Methods

Gradient-inspired methods import the abstraction of backpropagation into the
discrete text domain. Instead of computing numerical gradients, an LLM
generates natural-language critiques that play the role of error signals;
these critiques are then applied as textual updates to the prompt.

### 3.1 ProTeGi — Automatic Prompt Optimization with "Gradient Descent"

**Citation:** Pryzant et al., 2023 | EMNLP 2023 | arXiv:2305.03495

ProTeGi introduces the term *textual gradient*: a critique of the current
prompt generated by a separate LLM after observing examples on which the
prompt produced incorrect outputs. The textual gradient is then applied by a
second LLM call to rewrite the prompt.

**Core procedure:**

1. Run the current prompt on a minibatch of 64 examples; collect failures.
2. Pass the failed examples to a *gradient generator* prompt: "Here are
   examples where the prompt failed. What is wrong with the current prompt?"
3. Use the generator's critique to produce multiple candidate rewrites.
4. Apply Monte Carlo paraphrasing to expand the candidate pool.
5. Use beam search (width 4, depth 6, 8 expansions per parent) to select the
   highest-scoring candidate by validation accuracy.

**Datasets:** Ethos (hate-speech, 750/200 split), Liar (fake news, 3,681/461),
Jailbreak (custom safety classification, 200 test), Sarcasm (800/200).

**Models:** GPT-3.5-turbo as both gradient generator and scorer.

**Reported result:** F1 improvements of up to 31% over the initial prompt;
4–8% over Monte Carlo and RL baselines, averaged over 3 runs. Runtime
approximately 10 minutes per task.

### 3.2 TextGrad — Automatic "Differentiation" via Text

**Citation:** Yuksekgonul et al., 2024 | arXiv:2406.07496

TextGrad generalizes the ProTeGi idea into a full automatic-differentiation
framework for compound AI systems. Computation is modeled as a graph in which
each node holds a textual variable (a prompt, a generated answer, or an
intermediate output). A *backward pass* propagates LLM-generated critiques
from terminal nodes back through the graph; each variable is updated by
applying its incoming critique.

**Core mechanism:**

- Each node defines a forward pass (an LLM call, a tool call, an API request,
  or a Python function).
- A separate feedback LLM produces a critique of each node's output, which
  becomes the gradient for that node's input variables.
- Updates are applied iteratively (up to 10 iterations per task).
- A validation-based reversion mechanism rolls back updates that degrade
  performance.

**Tasks evaluated:**

| Task | Dataset | Split | Metric |
|---|---|---|---|
| Prompt optimization | MMLU-ML subset | 50 / 50 / rest | Accuracy |
| Prompt optimization | GSM8K | 100 / 100 / 300 | Accuracy |
| Code generation | HumanEval | Standard | Pass@1 |
| Science QA | GPQA Diamond | Full | Accuracy |
| Molecule generation | DOCKSTRING (58 targets) | All | Binding affinity |
| Medical planning | Radiotherapy plans | Case-based | Clinical criteria |

**Models:** Claude-3.5-Sonnet for the backward / feedback pass; GPT-4o-mini for
forward / task execution. Temperature 0 for evaluation, 1.0 for generation.

**Reported result:** approximately 9 absolute-point improvement over zero-shot
GPT-4o on GSM8K; matches best few-shot CoT.

### 3.3 GLaPE — Gradient-Like Prompt Evolution

**Citation:** Zhang et al., 2024

GLaPE combines textual-gradient feedback with an evolutionary outer loop. The
textual gradient produced from failures on a minibatch is used as one of
several mutation operators within a population-based search. The method
addresses an empirical instability of ProTeGi-style methods — that beam search
over LLM-generated critiques can stall in plateaus — by maintaining a diverse
population that resists premature convergence.

### Table 3.1 — Gradient-Inspired Methods

| Method | Optimizer / Feedback LLM | Scorer / Forward LLM | Update unit | Datasets reported | Key metric |
|---|---|---|---|---|---|
| ProTeGi | GPT-3.5-turbo | GPT-3.5-turbo | Beam search over rewrites | Ethos, Liar, Jailbreak, Sarcasm | F1 |
| TextGrad | Claude-3.5-Sonnet | GPT-4o-mini | Graph-wide backprop | MMLU, GSM8K, HumanEval, GPQA, DOCKSTRING | Accuracy, Pass@1 |
| GLaPE | LLM (variant-dependent) | LLM (variant-dependent) | Population mutation | BBH, GSM8K | Accuracy |

---

## 4. Evolutionary and Search-Based Methods

Evolutionary methods maintain a population of prompt candidates and apply
selection, mutation, and crossover operations across generations. LLMs
typically serve as the mutation and crossover operators; fitness is evaluated
against a labeled validation set.

### 4.1 EvoPrompt

**Citation:** Guo et al., 2023 | ICLR 2024 | arXiv:2309.08532

EvoPrompt applies classical evolutionary algorithms — Genetic Algorithm (GA)
and Differential Evolution (DE) — to prompt optimization, with an LLM as the
mutation / crossover operator.

**Core procedure:**

- Maintain a population of 10 prompt candidates.
- At each iteration: select parents by fitness, prompt the LLM to perform a
  *crossover* between two parent prompts (combining their traits) and a
  *mutation* of one prompt (paraphrasing or modifying).
- Evaluate offspring on a training set; select survivors by fitness.
- Run for 4 iterations.

**Datasets covered:** 31 datasets spanning classification, generation, and
reasoning, including SST-2/5 (sentiment), Antonyms / Cause-Selection /
Active-Passive (Instruction Induction), 5 BBH subtasks, SAMSum (summarization),
ASSET (simplification), and AG News.

**Models:** Alpaca-7B and GPT-3.5 as both task executor and optimizer.

**Reported result:** consistent improvements over human-designed prompts and
APE; the DE variant is more stable across tasks than the GA variant.

### 4.2 PromptBreeder

**Citation:** Fernando et al., 2023 | arXiv:2309.16797 (DeepMind)

PromptBreeder is a self-referential evolutionary method: not only the task
prompts but also the *mutation prompts* (the instructions used to mutate a task
prompt) are subject to evolution. The system maintains two populations —
task-prompts and mutation-prompts — and co-evolves them.

**Core procedure:**

- Initialize a population of task-prompts and a population of mutation-prompts.
- At each generation, a mutation-prompt operates on a task-prompt to produce a
  new task-prompt.
- Evaluate task-prompts on a held-out fitness set.
- Apply binary-tournament selection; replace the loser with a mutated copy of
  the winner.
- Periodically apply meta-mutations to the mutation-prompts themselves.

**Datasets:** GSM8K, SVAMP, MultiArith, AddSub, AQuA, ASDiv, and instruction
induction tasks. PaLM 2-L is the underlying LLM.

**Reported result:** outperforms hand-engineered prompts and Auto-CoT on most
arithmetic reasoning benchmarks; the self-referential element produces more
diverse exploration than fixed-mutation methods.

### 4.3 GEPA — Genetic-Pareto Prompt Evolution

**Citation:** Agrawal et al., 2025 | ICLR 2026 (Oral)

GEPA combines evolutionary search with Pareto multi-objective optimization. A
reflective LLM generates natural-language critiques after each generation; the
critiques guide the mutation operator. The Pareto-retention rule maintains a
diverse archive of prompts that trade off accuracy against other objectives
(length, diversity, faithfulness).

**Core procedure:**

- Maintain a population of (instruction, few-shot example) pairs.
- After each evaluation round, a reflective LLM critiques failures.
- Mutation is conditioned on the critique rather than random paraphrasing.
- The Pareto frontier is retained across generations.

**Reported result:** on a Qwen3 8B base, GEPA outperforms GRPO (24K rollouts)
by up to 20% using approximately 35× fewer rollouts. Average gain of +6%
across six tasks compared to MIPROv2. Sample-efficient: produces gains with as
few as 20–50 training examples.

### 4.4 PromptAgent

**Citation:** Wang et al., 2024 | ICLR 2024 | arXiv:2310.16427

PromptAgent treats prompt optimization as a Monte Carlo Tree Search (MCTS) over
expert-level prompts. Each node of the tree represents a prompt; edges
represent edits proposed by an LLM acting as an *agent* that incorporates error
feedback.

**Core procedure:**

- Initialize the tree with a baseline prompt at the root.
- At each step, expand a node by asking the LLM to edit the prompt based on a
  sample of failure cases.
- Evaluate each child on a validation set; back-propagate scores using the UCT
  rule.
- Repeat for a fixed number of MCTS iterations (typically 3 × 3 = 9 evaluation
  rounds).

**Datasets:** 6 BBH subtasks (Geometry, Causal, Penguins, Object Counting,
Epistemic, Temporal), NCBI / BC5CDR / ChemProt (biomedical NER and relation
extraction), Amazon (product classification), ISEAR (emotion).

**Models:** GPT-3.5-turbo as worker, GPT-4 as optimizer.

**Reported result:** average 9-point improvement over APE and CoT baselines on
BBH; strong results in biomedical domains.

### Table 4.1 — Evolutionary Methods

| Method | Population type | Selection rule | Mutation operator | Generations | Datasets |
|---|---|---|---|---|---|
| EvoPrompt (GA) | Task prompts | Fitness | LLM crossover + mutation | 4 | 31 datasets |
| EvoPrompt (DE) | Task prompts | Fitness | LLM differential variant | 4 | 31 datasets |
| PromptBreeder | Task + mutation prompts (co-evolved) | Binary tournament | Self-referential | Variable | GSM8K, SVAMP, MultiArith |
| GEPA | (instruction, exemplar) pairs | Pareto retention | Critique-conditioned LLM | Variable | 6 tasks, Qwen3 8B base |
| PromptAgent | Tree of prompts (MCTS) | UCT | LLM edit on failures | 3 iter × 3 children | BBH, biomedical, classification |

---

## 5. LLM-as-Optimizer Methods

The LLM-as-optimizer family casts a separate large language model as the
optimizer itself. The optimizer LLM observes a trajectory of (prompt, score)
pairs and proposes new candidate prompts. No explicit gradients, mutation
operators, or evolutionary populations are required; the optimizer's
general-purpose reasoning capability is leveraged directly. This family has
produced the largest number of recent methods and is the dominant mechanism in
current production-oriented systems.

This section is organized into per-method descriptions (§5.1–§5.7), a treatment
of the *dual-LLM* design pattern that recurs across the family (§5.8), and a
discussion of the *meta-prompt patterns* used to instruct the optimizer
(§5.9).

### 5.1 OPRO — Large Language Models as Optimizers

**Citation:** Yang et al., 2023 | ICLR 2024 | arXiv:2309.03409

OPRO is the canonical LLM-as-optimizer method. A meta-prompt is constructed at
each step containing: (a) a description of the optimization problem, (b) a
trajectory of past (instruction, score) pairs sorted by score, and (c) a small
number of training exemplars. The optimizer LLM generates new candidate
instructions from this meta-prompt.

**Core procedure:**

1. Initialize with a baseline prompt and an empty trajectory.
2. At each step, construct the meta-prompt with the top-20 historical
   (instruction, score) pairs and 3 random training exemplars.
3. Sample 8 new candidate instructions from the optimizer LLM at temperature
   1.0.
4. Evaluate each candidate on the training set (greedy decoding, temperature 0)
   and append the (instruction, score) pair to the trajectory.
5. Repeat for up to 100 steps; most tasks converge by step 20–40.

**Experimental setup:**

- GSM8K: ~261 examples sampled from the 7,473-example training split (3.5%)
  used for optimization; full 1,319-example test set used for evaluation.
- BBH (23 subtasks): approximately 100 training / 200 test examples per task.

**Models:**

| Role | Models tested |
|---|---|
| Optimizer | PaLM 2-L (pre-trained), PaLM 2-L-IT, text-bison, GPT-3.5-turbo, GPT-4 |
| Scorer | PaLM 2-L (pre-trained), text-bison |

**Reported results:**

- Up to 8 absolute-point improvement over human-designed prompts on GSM8K.
- Outperforms zero-shot CoT on 19/23 BBH tasks by more than 5 absolute points
  (PaLM 2-L scorer).
- The instruction *"Take a deep breath and work on this problem
  step-by-step."* emerged as the top GSM8K prompt under one configuration.

**Notable ablations in the original paper:**

- Trajectory ordering (ascending vs. descending score order).
- Instruction position in the prompt (beginning vs. end).
- Overfitting analysis (optimization-set accuracy vs. test accuracy).
- Comparison with EvoPrompt's meta-prompt style.

### 5.2 PE2 — Prompt Engineer Squared

**Citation:** Ye et al., 2024 | arXiv:2311.05661 | NAACL 2024

PE2 investigates the use of GPT-4 as an optimizer for GPT-4 itself. It
introduces a *meta-meta-prompt* that instructs the optimizer how to optimize —
for example, how to use error analysis, how to apply step-by-step reasoning in
its critiques, and how to decompose the optimization problem.

**Datasets:** GSM8K (primary, 100 / 300 train / test), BBH (six subtasks).

**Models tested for transfer:** text-davinci-003 (primary), GPT-3.5,
Mistral-7B, Yi-6B.

**Notable empirical finding:** prompts optimized for one model do not reliably
transfer to other models. A prompt that produces strong accuracy under
text-davinci-003 may perform substantially worse under Mistral-7B or Yi-6B
without re-optimization. This model-specificity result has implications for
any APO deployment that swaps the underlying LLM.

### 5.3 SAMMO — Structure-Aware Multi-Objective Metaprompt Optimization

**Citation:** Schnabel & Neville, 2024 | Microsoft Research

SAMMO formalizes prompts as structured trees with labeled components
(instructions, format specifications, examples, output schemas) rather than as
flat strings. Mutations are applied at the structural level — for instance,
swapping a *format-hint* subtree with an alternative, or reordering example
components — allowing the optimizer to explore the prompt structure space
rather than the free-text space.

**Core mechanism:**

- Prompts are parsed into a labeled tree with components such as `{role}`,
  `{instructions}`, `{format}`, `{examples}`.
- A library of mutation operators is defined per component type.
- An LLM (or a beam search) selects the next mutation conditioned on the
  current tree and the validation feedback.
- Multiple objectives (accuracy, latency, length) are tracked simultaneously.

**Reported result:** SAMMO matches or exceeds APE and OPRO on classification,
NER, and summarization benchmarks, while producing prompts that are noticeably
shorter — a structural side-effect of explicit component-level optimization.

### 5.4 PRewrite

**Citation:** Kong et al., 2024 | arXiv:2401.08189

PRewrite trains a small *rewriter* LLM via reinforcement learning to transform
a base prompt into an optimized prompt. The base prompt and the optimized
prompt are run on the same task; the reward is the resulting accuracy gain.
PPO is used as the RL algorithm.

**Core mechanism:**

- Input: a base task prompt $p_0$.
- Rewriter model $R(\cdot)$ (initialized from a small pre-trained LLM, e.g.,
  T5-base or Llama-3-8B) produces an optimized prompt $p^* = R(p_0)$.
- The downstream task model executes both $p_0$ and $p^*$ on a training batch;
  reward equals $\text{score}(p^*) - \text{score}(p_0)$.
- PPO updates the rewriter's parameters.

**Datasets:** NLG and NLU tasks from GLUE / SuperGLUE families plus reasoning
subsets.

**Notable property:** once trained, $R$ generalizes — it can rewrite previously
unseen base prompts without further training. This contrasts with online
methods like OPRO, which must rerun the optimization loop for each new prompt.

### 5.5 BPO — Black-Box Prompt Optimization

**Citation:** Cheng et al., 2024 | arXiv:2311.04155

BPO fine-tunes a small language model (typically Llama-2-7B) to act as a
universal prompt rewriter. The training set is constructed by collecting
(bad-prompt, good-prompt, response-quality) triples mined from large-scale
preference data (e.g., Anthropic HH, OpenAssistant). The small model learns to
map a bad prompt to a good prompt that maximizes downstream response quality.

**Core mechanism:**

- Mine preference data to identify cases where a slight rewording of the
  user's prompt yields a better response.
- Supervised fine-tuning on these (original, optimized) pairs.
- At inference time, the BPO model is applied to each new user prompt before
  it reaches the downstream LLM.

**Reported result:** BPO improves response quality across a range of
downstream models (GPT-3.5, GPT-4, Llama-2) without modifying the downstream
model itself. Costs are amortized: a single rewriter generalizes across users
and tasks.

### 5.6 FIPO — Free-form Instruction-oriented Prompt Optimization

**Citation:** Lu et al., 2024

FIPO follows the BPO pattern of training a dedicated rewriter, but specializes
the training data to instruction-following tasks. The rewriter is trained on a
curated corpus of (instruction, optimized-instruction, quality-score) triples
generated by stronger LLMs (GPT-4) and filtered by automatic quality metrics.

**Notable property:** targets instruction-tuned models specifically and
reports gains on AlpacaEval and MT-Bench rather than reasoning benchmarks.

### 5.7 StablePrompt

**Citation:** 2024

StablePrompt addresses an empirical observation: many APO methods produce
prompts whose validation accuracy oscillates substantially across iterations,
leading to test-time underperformance. The method introduces a *stability
regularizer* — measured by the variance of accuracy across cross-validation
folds — that penalizes candidates with high variance even if their mean
accuracy is high.

**Reported property:** lower variance and modest accuracy gains over OPRO
baselines on BBH and MMLU subsets.

### 5.8 The Dual-LLM Discipline

Across the LLM-as-optimizer family, a recurring design choice is the
separation of *optimizer* and *scorer* (also referred to as *forward* and
*backward*, or *worker* and *judge*) models. The pattern is sufficiently
widespread to warrant explicit treatment.

**Definition:** in a dual-LLM configuration, the model that proposes new
prompts is distinct from the model that executes them on the task. The
optimizer typically runs at higher temperature (1.0) for diversity; the scorer
runs at temperature 0 for deterministic evaluation. The two models may be
different sizes (a large optimizer with a small scorer, or vice versa),
different architectures, or different APIs.

### Table 5.1 — Documented Dual-LLM Configurations

| Method | Optimizer / Critic | Scorer / Worker | Rationale stated in paper |
|---|---|---|---|
| ProTeGi | GPT-3.5-turbo | GPT-3.5-turbo | Same model; temperature only |
| TextGrad | Claude-3.5-Sonnet | GPT-4o-mini | Strong critic, cheap executor |
| OPRO | PaLM 2-L / GPT-4 | PaLM 2-L (pre-trained) / text-bison | Decoupled to study transfer |
| PromptAgent | GPT-4 | GPT-3.5-turbo | Expert critic, cheap worker |
| PE2 | GPT-4 | GPT-4, Mistral-7B, Yi-6B | Self-optimization + transfer study |
| GEPA | LLM (reflective) | LLM (task) | Critique-conditioned mutation |

**Reasons for the separation:**

1. *Cost.* A large optimizer is invoked only at update steps; a cheap scorer
   runs on every minibatch.
2. *Bias.* A self-evaluating model can inflate its own scores; an independent
   scorer reduces this.
3. *Stability.* The optimizer's stochasticity (high temperature) is contained
   behind a deterministic evaluator.
4. *Transferability studies.* Separating the two models permits ablations that
   measure how much of the gain comes from optimizer capability versus scorer
   capability (a question explored explicitly by PE2).

**Failure modes documented in the literature:**

- *Judge bias toward verbosity.* Scorer LLMs may favor longer or more
  confident outputs even when correctness is identical (a finding from the
  broader LLM-as-judge literature).
- *Optimizer-scorer mismatch.* When the optimizer is much stronger than the
  scorer, optimized prompts may exploit scorer weaknesses rather than improve
  true task accuracy.
- *Positional bias.* Scorers asked to compare two outputs in sequence may
  prefer the first or last presented (an effect documented in MT-Bench
  analyses).

### 5.9 Meta-Prompt Engineering Patterns

A second recurring design choice within the LLM-as-optimizer family is the
construction of the *meta-prompt* — the prompt sent to the optimizer that
instructs it to propose new task prompts. Three patterns dominate.

**Pattern A — Trajectory-based (OPRO style):**

> "The previous instructions and their scores are: [trajectory]. Generate a
> new instruction that scores higher. Some training exemplars: [exemplars]."

**Pattern B — Error-analysis (ProTeGi / GEPA style):**

> "The current instruction is: [prompt]. It produced the following incorrect
> outputs on these examples: [failures]. What is wrong with the instruction,
> and how should it be rewritten?"

**Pattern C — Component-edit (SAMMO style):**

> "The current prompt has these labeled components: [tree]. Propose an edit to
> component [target] that addresses the following weakness: [weakness]."

Empirical studies — notably OPRO's own ablation and PE2's meta-meta-prompt
analysis — report that meta-prompt design has first-order influence on
optimizer output quality. A poorly constructed meta-prompt can erase most of
the gains otherwise expected from the family.

### Table 5.2 — LLM-as-Optimizer Methods (Expanded)

| Method | Year | Meta-prompt style | Optimizer model | Scorer model | Convergence budget | Datasets reported | Notable result |
|---|---|---|---|---|---|---|---|
| OPRO | 2023 | Trajectory | PaLM 2-L, GPT-3.5, GPT-4 | PaLM 2-L, text-bison | ≤100 steps | GSM8K, BBH (23 tasks) | +8 abs. on GSM8K vs. human |
| PE2 | 2024 | Meta-meta-prompt | GPT-4 | GPT-4, Mistral-7B, Yi-6B | Variable | GSM8K, BBH (6 tasks) | Transferability is poor |
| SAMMO | 2024 | Component-edit | LLM (variant) | Task model | Beam search | Classification, NER, summarization | Shorter prompts at parity |
| PRewrite | 2024 | RL-trained rewriter | T5 / Llama-3-8B (PPO) | Task model | One forward pass | GLUE / SuperGLUE family | Generalizes without re-train |
| BPO | 2024 | SFT-trained rewriter | Llama-2-7B | GPT-3.5, GPT-4, Llama-2 | One forward pass | Anthropic HH, OpenAssistant | Universal rewriter |
| FIPO | 2024 | SFT-trained rewriter | Small LM | Instruction-tuned LLM | One forward pass | AlpacaEval, MT-Bench | Instruction-following gains |
| StablePrompt | 2024 | Stability-regularized | LLM | LLM | Variable | BBH, MMLU | Lower variance |
| GEPA (cross-listed) | 2025 | Critique-conditioned | LLM | LLM | Few generations | 6 tasks, Qwen3 8B | 35× fewer rollouts vs. GRPO |

---

## 6. Framework-Level Optimizers

Framework-level optimizers are not standalone algorithms; they are libraries
that provide a programmatic abstraction for compound LLM pipelines and bundle
one or more APO algorithms as *compilers* or *teleprompters* that
automatically tune both instructions and few-shot demonstrations across the
pipeline.

### 6.1 DSPy

**Citation:** Khattab et al., 2023 | ICLR 2024 | arXiv:2310.03714

DSPy provides Python primitives (`dspy.Module`, `dspy.Signature`,
`dspy.Predict`) for declaring LLM pipelines as composable modules. Once a
pipeline is declared, one of several built-in optimizers can be invoked to
tune the entire pipeline against a user-defined metric.

#### 6.1.1 BootstrapFewShot

The simplest optimizer in the DSPy stack: run the pipeline on the training
set, collect traces where the final output matches the gold answer, and use
the high-quality traces as few-shot demonstrations for each predictor. No
instruction optimization is performed.

#### 6.1.2 COPRO — Cooperative Prompt Optimization

A beam-search APO method built into DSPy. At each step, the LLM generates
multiple new candidate instructions for each predictor based on the $N$ best
prompts so far; candidates are evaluated on the training set; the top-$K$ are
retained.

**Typical configuration:** 20–200 training examples, breadth 8, depth 3,
user-defined metric.

#### 6.1.3 MIPROv2 — Multi-stage Instruction Prompt Optimization v2

**Citation:** Opsahl-Ong et al., 2024 | arXiv:2406.11695

MIPROv2 is a three-stage pipeline:

1. *Bootstrap* — run the pipeline on training data, collect high-scoring
   traces as few-shot demonstrations.
2. *Proposal* — an LLM generates multiple candidate instructions per
   predictor, conditioned on dataset summaries and observations drawn from
   bootstrapped traces.
3. *Bayesian search* — Optuna's TPE sampler searches over combinations of
   (instruction, demonstrations) that maximize the metric on mini-batches.

**Experimental conventions:**

- 90 / 10 train / validation split from the original training partition; the
  test set is never used during optimization.
- The few-shot demonstration pool is drawn from the training split only.
- 10–25 candidate instructions per predictor.
- Search budgets: 13 trials (light), ~50 trials (medium), ~200+ trials
  (heavy).

**Default models in published experiments:** GPT-4o-mini, Llama-3.1-8B,
Gemini 1.5 Flash. Temperature 0 for evaluation, 1.0 for generation.

**Datasets reported in the DSPy line of work:**

| Dataset | Task | Train | Val | Test | Metric |
|---|---|---|---|---|---|
| GSM8K | Math reasoning | 7,473 (capped at 200) | 10% holdout | 1,319 | EM |
| HotPotQA | Multi-hop QA | 500 | 50 | 7,405 | F1 |
| MultiHop RAG (custom) | RAG | 200 | 50 | 200 | Answer match |
| LegalBench (definition class.) | Legal | 80–100 | 40 | 200 | Accuracy |
| MedQA | Medical | 100 | 50 | 1,273 | Accuracy |

**Reported result:** MIPROv2 consistently outperforms COPRO and OPRO within
the DSPy framework. The *heavy* mode produces the strongest accuracy at 3–5×
the cost of *medium*.

#### 6.1.4 SIMBA — Stochastic Mini-Batch Ascent

**Citation:** DSPy team, 2025

SIMBA performs online stochastic mini-batch optimization within the DSPy
framework. At each step it samples a random mini-batch, identifies the
predictor whose update most improves the batch metric, and applies that
update. Reported as more sample-efficient than MIPROv2 on pipelines with many
predictors.

### 6.2 TextGrad as a Framework

Beyond its role as a gradient-inspired algorithm (Section 3.2), TextGrad is
also published as a Python library that exposes the computation-graph
abstraction directly. Users wrap LLM calls in `tg.LLM` nodes, declare textual
variables with `tg.Variable`, and call `.backward()` to propagate critiques.
The library has been adopted in molecular design and clinical-planning case
studies.

### 6.3 Other Frameworks

- **LangChain prompt optimizers.** LangChain provides a `PromptHub` and
  several optimizer wrappers; most wrap OPRO-style trajectory loops or
  APE-style generate-and-score procedures.
- **Promptify / Guidance.** Prompt templating frameworks that include
  automatic instruction-induction utilities but do not provide full APO
  pipelines.

### Table 6.1 — Framework-Level Optimizers

| Framework | Optimizer | Mechanism | Inputs | Output |
|---|---|---|---|---|
| DSPy | BootstrapFewShot | Trace mining | Pipeline + metric | Few-shot demos |
| DSPy | COPRO | Beam search | Pipeline + metric | Instructions |
| DSPy | MIPROv2 | Bayesian (TPE) | Pipeline + metric + dataset | Instructions + demos |
| DSPy | SIMBA | Stochastic mini-batch | Pipeline + metric | Per-predictor updates |
| TextGrad | TextGrad | Graph backprop | Computation graph | All textual variables |
| LangChain | Various | Wrapped OPRO / APE | LLM chain | Instructions |

---

## 7. Feedback and Human-Signal Methods

This family uses feedback — from the model itself, from human evaluators, or
from a learned preference function — as the primary optimization signal. The
methods differ in who provides the feedback and how it is integrated.

### 7.1 Self-Refine

**Citation:** Madaan et al., 2023 | NeurIPS 2023 | arXiv:2303.17651

Self-Refine uses a single LLM to generate an output, critique its own output,
and refine it based on the self-critique. The loop is repeated for a fixed
number of iterations (typically 3–5).

**Procedure:**

1. Generate $y_0 = M(x)$ on input $x$.
2. Critique $c_0 = M(\text{critique-prompt}(x, y_0))$.
3. Refine $y_1 = M(\text{refine-prompt}(x, y_0, c_0))$.
4. Repeat $y_1 \to c_1 \to y_2 \to \ldots$ for $T$ iterations.

**Datasets:** GSM8K, HumanEval (code), Dialogue Response Generation, Math
Reasoning.

**Reported result:** iterative self-refinement yields consistent improvements
over single-pass generation across tasks. No prompt template is updated — only
the output is refined per inference.

### 7.2 AutoHint

**Citation:** Sun et al., 2023

AutoHint summarizes feedback from a batch of incorrect inferences into a small
set of natural-language *hints*, which are then injected into the original
prompt as few-shot guidance. The hints are produced by an LLM that observes
the failures and is asked to extract reusable patterns.

### 7.3 CRISPO — Critique-Suggestion Prompt Optimization

**Citation:** He et al., 2025

CRISPO uses a multi-aspect critique meta-prompt to generate critiques along
several dimensions simultaneously — style, precision, content alignment,
format. Aspect-specific suggestions are then aggregated into a single prompt
update. The aspect-decomposition is reported to produce more targeted
improvements than monolithic critique prompts.

### 7.4 GATE — Guided Automatic Text Engineering

**Citation:** Joko et al., 2024

GATE uses human ratings (on a Likert scale) of (prompt, output) pairs as the
optimization signal. A rewriter LLM adjusts the prompt based on the aggregated
ratings. The signal is richer than binary correctness, but the collection
burden scales with the number of optimization rounds.

### 7.5 PLHF — Prompt Learning with Human Feedback

**Citation:** ~2024

PLHF formalizes prompt optimization as Bayesian optimization over a learned
human-preference function. The procedure has three components:

1. Human experts rate (input, output) pairs, producing a labeled preference
   dataset.
2. A surrogate model is trained to predict human preference from prompt and
   output.
3. A black-box optimizer rewrites the prompt to maximize predicted preference.

**Training scale:** 50–200 labeled pairs to train the surrogate; the surrogate
is then queried at no human cost for candidate evaluation.

### 7.6 APOHF — Automatic Prompt Optimization with Human Feedback

**Citation:** Lin et al., 2024 | arXiv:2405.17346 | NeurIPS 2024

APOHF treats prompt optimization as a dueling-bandit problem with
human-preference feedback. At each round, the optimizer proposes two candidate
prompts; a human (or a preference oracle) indicates which is preferred; the
bandit updates its belief over the prompt space and proposes the next pair.

**Procedure:**

- Maintain a set of arms (prompt candidates) and a Bayesian estimate of their
  pairwise preference probabilities.
- At each round, select an arm pair via the dueling-bandit policy (e.g.,
  Double Thompson Sampling).
- Receive a binary preference from the human; update the posterior.
- After $T$ rounds, return the arm with the highest estimated preference.

**Reported settings:** open-ended text generation, customer-service dialog,
instruction-following tasks.

**Notable property:** requires no scalar reward — only pairwise comparisons,
which are easier to elicit reliably from human annotators.

### Table 7.1 — Feedback and Human-Signal Methods

| Method | Feedback source | Feedback type | Aggregation | Output |
|---|---|---|---|---|
| Self-Refine | The model itself | Free-text critique | Same-model refine call | Output refinement (not prompt) |
| AutoHint | Failure batch | Pattern extraction | Hint injection | Updated prompt |
| CRISPO | Critique LLM | Multi-aspect critique | Aspect-merged rewrite | Updated prompt |
| GATE | Human | Likert rating | LLM rewriter | Updated prompt |
| PLHF | Human | Pairwise / scalar | Trained surrogate + BO | Updated prompt |
| APOHF | Human | Pairwise | Dueling bandit | Updated prompt |

---

## 8. Data-Aware and Runtime-Adjacent Methods

A small but growing subset of recent methods focuses on *which* examples to
use during optimization, rather than the optimization mechanism itself. The
motivation is empirical: APO methods waste budget on examples that contribute
little to learning.

### 8.1 APEX — Automated Prompt Engineering eXpert with Dynamic Data Selection

**Citation:** Wang et al., 2026 | arXiv:2606.11459

APEX classifies training examples by *optimization lineage* — how they behave
under the current population of candidate prompts:

- *Easy* — solved by all candidates; uninformative for mutation.
- *Hard* — solved by none; uninformative as noise.
- *Mixed* — solved by some but not all candidates; maximum discriminative
  signal.

Optimization budget is concentrated on the Mixed tier for two purposes:

- *Addressable frontier* — prompt mutations are generated to target Mixed-tier
  failures.
- *Rank-sensitive frontier* — Mixed-tier examples are used to rank candidate
  quality.

**Reported result (under a fixed 5,000 evaluation-call budget):**

- +11.2 absolute points on Gemini 2.5 Flash.
- +6.8 absolute points on Gemma 3 27B.

### 8.2 ETGPO — Error Taxonomy-Guided Prompt Optimization

**Citation:** 2026 | arXiv:2602.00997

ETGPO collects errors from failed traces, classifies them into a taxonomy of
error categories (e.g., misidentified entity, wrong reasoning step, format
error), filters to the most prevalent categories, generates actionable
guidance for each, and combines the guidance into the final optimized prompt.

**Procedure:**

1. Run the current prompt on a validation set; collect failure traces.
2. An LLM classifier assigns each failure to an error category.
3. Filter to categories with prevalence above a threshold.
4. Generate one actionable guidance sentence per surviving category.
5. Append all guidance into the prompt.

**Datasets:** BBH, GPQA Diamond, LegalBench definition-classification.

**Reported result:** taxonomy-guided guidance provides more stable
improvements than reflective evolutionary methods at lower compute, and is
comparable to MIPROv2 *heavy* mode.

### 8.3 Other Data-Aware Variants

A small body of work explores *dynamic example selection* during APO — for
instance, choosing few-shot demonstrations on a per-input basis at inference
time. Methods include retrieval-based selection ($k$NN over training set),
uncertainty-based selection (highest-entropy examples), and active-learning
loops that re-label examples between optimization rounds.

---

## 9. Evaluation-Focused Methods

A separate strand of recent work focuses on evaluation rather than
optimization: how to score a candidate prompt without running it on the full
validation set, and how to compute structured quality scores for
retrieval-augmented generation (RAG) outputs.

### 9.1 Execution-Free Evaluation

**Citation:** 2025 | arXiv:2511.19829 — *"Knowing How to Edit: Evaluation-Instructed Prompt Optimization"*

This work proposes that evaluation and optimization should be unified — the
evaluator explicitly instructs the optimizer how to fix the prompt. Two
components:

1. *Execution-free evaluator* — a small trained model that predicts prompt
   quality directly from text, without running the prompt. Designed to avoid
   repeated expensive LLM calls.
2. *Evaluation-instructed optimization* — the evaluator generates structured
   critique that tells the optimizer *which aspect* to fix rather than only
   that the prompt is poor.

**Experimental setup:**

| Dataset | Role | Train | Test |
|---|---|---|---|
| BBH (subset) | In-distribution | 100 | 100 |
| GPQA Diamond | In-distribution | 100 | 100 |
| LegalBench definition class. | In-distribution | 100 | 100 |
| MATH500 | Unseen generalization | 0 | 200 |
| MedQA | Unseen generalization | 0 | 200 |

**Reported result:** the execution-free evaluator matches full-execution
evaluation at approximately 10% of the compute cost.

### 9.2 RAGAS

**Citation:** Es et al., 2024 | EACL 2024 | arXiv:2309.15217

RAGAS provides a framework of structured metrics for RAG pipelines:
*faithfulness* (answer is grounded in retrieved context), *answer relevance*
(answer matches the question), *context precision*, and *context recall*. Each
metric is computed by an LLM judge with a calibrated prompt. RAGAS has become
the de facto evaluation standard for retrieval pipelines and is frequently
used as a downstream metric in prompt-optimization experiments that involve
retrieval.

### 9.3 LLM-as-Judge Protocols

Independent of any specific paper, the broader literature has converged on a
set of protocols for LLM-based judging:

1. The judge is prompted with the question, the gold answer (when available),
   and the candidate output, and asked for a verdict plus one-sentence
   justification.
2. The judge is validated against 100–200 human annotations; Cohen's
   $\kappa \geq 0.7$ is treated as acceptable agreement.
3. The judge model is typically chosen to be at least as strong as the task
   model (GPT-4o, Claude Sonnet, or Llama-3-70B-Instruct).
4. Position swap and pairwise duplication are used to test for positional
   bias (MT-Bench convention).

---

## 10. Datasets Reference

The following datasets appear repeatedly across the APO literature. The
*Representative methods* column lists papers that use the dataset; this is not
exhaustive.

### Table 10.1 — Datasets Used in APO Literature

| Dataset | Domain | Train / Test | Task type | Standard metric | Representative methods |
|---|---|---|---|---|---|
| GSM8K | Math reasoning | 7,473 / 1,319 | Generation (multi-step) | Exact Match | APE, OPRO, ProTeGi, MIPROv2, TextGrad, GEPA |
| BBH (23 subtasks) | Multi-step logic | ~250 / 250 per task | Mixed | Accuracy | OPRO, APE, PromptAgent, MIPROv2 |
| BIG-Bench Instruction Induction | Instruction following | 10 demo / 50 | Mixed | Accuracy | APE, EvoPrompt |
| MMLU | General knowledge | ~100K / 14K | Multi-choice | Accuracy | TextGrad, DSPy |
| StrategyQA | Commonsense | 2,290 / 490 | Yes / No | Accuracy | APE, OPRO |
| AQuA-RAT | Algebraic QA | 97,467 / 254 | Multi-choice | Accuracy | OPRO, PE2 |
| Natural Questions | Open-domain QA | 79,168 / 3,610 | Generation | EM + F1 | RAG-line methods |
| HotPotQA | Multi-hop QA | 90,447 / 7,405 | Generation | EM + F1 | DSPy, RAG-line methods |
| LegalBench (162 tasks) | Legal reasoning | ~500 / variable | Mixed | Accuracy | DSPy, *Knowing How to Edit*, ETGPO |
| MedQA | Medical licensing | 10,178 / 1,273 | Multi-choice | Accuracy | *Knowing How to Edit* |
| GPQA Diamond | Graduate science | 198 / ~50 | Multi-choice | Accuracy | TextGrad, ETGPO |
| HumanEval | Code generation | 0 / 164 | Generation | Pass@1 | TextGrad, FIPO |
| MATH500 | Competition math | 500 | Generation | EM | *Knowing How to Edit* |
| Ethos | Hate speech | 750 / 200 | Binary | F1 | ProTeGi |
| Liar | Fake news | 3,681 / 461 | Binary | Accuracy | ProTeGi |
| SST-2 / SST-5 | Sentiment | 67,349 / 872 | Classification | Accuracy | EvoPrompt |
| SAMSum | Summarization | 14,732 / 819 | Generation | ROUGE-L | EvoPrompt |
| ASSET | Text simplification | — / 359 | Generation | SARI | EvoPrompt |
| AG News | Classification | 120,000 / 7,600 | 4-class | Accuracy | EvoPrompt |
| AlpacaEval / MT-Bench | Instruction following | — | Pairwise | Win-rate | FIPO, BPO |

---

## 11. Evaluation Protocols

### 11.1 Standard Metrics

| Task type | Primary metric | Secondary metric | Notes |
|---|---|---|---|
| Reasoning (GSM8K, MATH) | Exact Match | — | Final numerical answer only |
| Multi-step logic (BBH) | Accuracy | Per-subtask breakdown | 23 subtasks |
| Classification | Accuracy or F1 | Per-class F1 | Binary tasks: accuracy is sufficient |
| QA (NQ, HotPotQA) | EM | F1 | EM strict; F1 lenient |
| Generation (summarization) | ROUGE-L | BERTScore | Human evaluation at top venues |
| Code | Pass@1 | Pass@10 | HumanEval / MBPP convention |
| RAG | Faithfulness, Answer Relevance | Context Precision / Recall | RAGAS framework |
| Instruction following | Pairwise win-rate | Accuracy | AlpacaEval, MT-Bench convention |

### 11.2 Standard Splits

| Dataset | Typical APO split | Comment |
|---|---|---|
| GSM8K | ~100–200 train / 200–300 val / 1,319 test | Sample from the 7,473 training partition |
| BBH | 100 train / 50 val / 200 test per task | Some papers use a 5,808 / 703 all-task split |
| MMLU | Subsample of 6 subjects, 2:2:6 ratio | Variable across papers |
| LegalBench | ~500 average per task; train / test resampled freely | Permitted by the benchmark |
| MedQA | Often used zero-shot for generalization probes | 10,178 / 1,273 official |
| HotPotQA | 500 train / 50 val / 200–7,405 test | Dev set is treated as test in most APO papers |

### 11.3 Reproducibility Norms at Top Venues

Across recent ACL, EMNLP, NeurIPS, and ICLR submissions, the following are
increasingly standard:

- **≥3 random seeds**, with mean ± standard deviation reported.
- **Separate optimizer and scorer models**, to prevent self-evaluation
  circularity.
- **Temperature 0 for evaluation; 1.0 for generation / optimization** unless
  an ablation requires otherwise.
- **Ablation table** covering at minimum: feedback signal type, training set
  size, threshold / budget sensitivity, optimizer / scorer model swap.
- **Budget comparison**: accuracy per $N$ evaluation calls reported alongside
  final accuracy.
- **Paired significance test** ($t$-test or Wilcoxon) across seeds for any
  claim of improvement over a baseline.

### 11.4 LLM-as-Judge Protocol

When ground truth is unavailable, or the task is open-ended, the following
protocol is widely adopted:

1. *Prompt the judge.* "Given the question $Q$, the gold answer $A$ (if any),
   and the model output $O$, is $O$ correct? Respond Yes or No with a
   one-sentence justification."
2. *Validate the judge.* Collect 100–200 human annotations on a sample;
   compute Cohen's $\kappa$. $\kappa \geq 0.7$ is treated as strong agreement.
3. *Choose a strong judge.* GPT-4o, Claude-3.5-Sonnet, or Llama-3-70B-Instruct
   are common choices. Weaker models introduce systematic biases (verbosity
   preference, positional bias).
4. *Apply position swaps and pairwise duplication* for pairwise judgments to
   detect positional bias.
5. *For RAG outputs*, prefer the RAGAS framework, which wraps these heuristics
   in structured metrics.

### Table 11.1 — Reproducibility Norms by Venue

| Venue | Seeds | Optimizer ≠ scorer | Ablation table | Significance test | Budget reporting |
|---|---|---|---|---|---|
| ACL / EMNLP / NAACL | ≥3 | Encouraged | Required | Required | Encouraged |
| NeurIPS / ICML / ICLR | ≥3 | Encouraged | Required | Required | Required |
| COLM / TMLR | ≥3 | Encouraged | Encouraged | Encouraged | Encouraged |
| Industry tracks (EMNLP-Industry, NAACL-Industry, KDD-AD) | ≥1 | Optional | Encouraged | Optional | Required |

---

## 12. Cross-Cutting Summary

### Table 12.1 — Methods by Mechanism

| Mechanism | Representative methods | Mechanism summary |
|---|---|---|
| Discrete gradient search | AutoPrompt | HotFlip-style token replacement |
| Generate-and-score | APE, Auto-CoT | LLM proposes candidates, scored on validation |
| Textual gradient | ProTeGi, TextGrad, GLaPE | LLM critique as gradient analogue |
| Evolutionary | EvoPrompt, PromptBreeder, GEPA | Population + mutation + selection |
| Tree search | PromptAgent | MCTS over edits |
| LLM-as-optimizer | OPRO, PE2, SAMMO, PRewrite, BPO, FIPO, StablePrompt | Optimizer LLM with trajectory or rewriter model |
| Framework-level | DSPy (COPRO, MIPROv2, SIMBA), TextGrad | Pipeline-aware tuning |
| Self-feedback | Self-Refine, AutoHint, CRISPO | Same model critiques itself |
| Human-feedback | GATE, PLHF, APOHF | Human preference signals |
| Data-aware | APEX, ETGPO | Selection of which examples drive updates |
| Evaluation-focused | *Knowing How to Edit*, RAGAS | Score-without-execution; structured metrics |

### Table 12.2 — Methods by Signal Source

| Primary signal | Methods |
|---|---|
| Task accuracy (gold labels) | AutoPrompt, APE, EvoPrompt, PromptBreeder, OPRO, PE2, SAMMO, COPRO, MIPROv2, SIMBA, PromptAgent, StablePrompt, APEX, ETGPO |
| LLM-generated critique | ProTeGi, TextGrad, GLaPE, GEPA, AutoHint, CRISPO |
| Self-critique (single-model) | Self-Refine |
| Human feedback (rated / paired) | GATE, PLHF, APOHF |
| Distilled preference data | BPO, FIPO, PRewrite |
| Execution-free evaluator | *Knowing How to Edit* |

### Table 12.3 — Methods by Year

| Year | Methods |
|---|---|
| 2020 | AutoPrompt |
| 2022 | CoT, Zero-shot CoT, Auto-CoT, APE |
| 2023 | ProTeGi, EvoPrompt, PromptBreeder, OPRO, PromptAgent, DSPy, Self-Refine, AutoHint, BPO |
| 2024 | TextGrad, PE2, SAMMO, PRewrite, FIPO, StablePrompt, GLaPE, MIPROv2, GATE, PLHF, APOHF, RAGAS |
| 2025 | GEPA, SIMBA, CRISPO, *Knowing How to Edit* |
| 2026 | APEX, ETGPO |

---

*End of literature survey.*
*Approximate coverage: 30+ methods, 18 datasets, 11 tables.*

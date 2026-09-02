# Datasets and Benchmarks: Per-Dataset Comparison Tables

**Companion to** [`literature_review.md`](literature_review.md) (method-centric
literature review) and
[`four_paper_grilling_and_finish_plan.md`](four_paper_grilling_and_finish_plan.md)
(FDPO-specific critique and finish plan). Where that document is organized
method-first ("what does GEPA do"), this document is organized
**dataset-first** ("what has been reported on GSM8K"), grouped by benchmark
family. It contains tables only; add new datasets to the matching family
below rather than creating a new file.

## How to read these tables

| Column | Meaning |
|---|---|
| Paper / Method | Who ran this dataset and with which algorithm |
| Train / Test (scale) | The split sizes actually used for that run, not the full corpus size unless stated |
| Mechanism | One-line description of the optimization mechanism applied |
| Failure Signal to Optimizer? | **Y** = raw failed inputs/outputs shown to the proposer; **N** = only a scalar score or no optimizer at all; **Partial** = some failure information reaches the proposer indirectly; a short "how" follows |
| LLM(s) Used | Executor/solver model, and proposer/critic/reflection model when distinct |
| Results (Before -> After) | Reported baseline versus final metric; multi-metric rows are separated by `/` |
| Notes | Caveats, seed counts, leakage warnings, or "not reported" markers |

"Not reported" means the reviewed materials describe the method using this
dataset but did not capture a specific number; it is not a zero and should
not be treated as one. "n/a" means the column does not apply to that row
(for example, a pure RL weight-update baseline has no rewritten prompt to
describe a Mechanism/Failure-Signal column for in the usual sense).

---

## 1. Math and Arithmetic Reasoning

### 1.1 GSM8K

| Paper / Method | Train / Test (scale) | Mechanism | Failure Signal to Optimizer? | LLM(s) Used | Results (Before -> After) | Notes |
|---|---|---|---|---|---|---|
| APE | ~3.5% of 7,473 train (~261) for CoT discovery / full 1,319 test | Generate-and-score candidate CoT triggers, iterative paraphrase | N (scalar validation score) | text-davinci-001/002 (generator + scorer) | 40.7% -> 43.0% (+2.3pp), discovered CoT trigger vs. hand-written "Let's think step by step" | Single best-trigger comparison, not a full optimization loop per example |
| OPRO | ~261 of 7,473 train (3.5%) / full 1,319 test | Trajectory-based LLM-as-optimizer meta-prompt (top-20 past prompt/score pairs + 3 exemplars) | N (score trajectory only) | Optimizer: PaLM 2-L / GPT-3.5 / GPT-4; Scorer: PaLM 2-L / text-bison | Up to +8pp vs. human-designed prompt baseline (exact baseline % not reported in reviewed materials) | Discovered prompt: "Take a deep breath and work on this problem step-by-step." |
| TextGrad | 100 train / 100 val / 300 test | Computation-graph textual backpropagation, validation-based reversion | Y (critique derived from graph-node outputs, propagated as textual gradients) | Backward/critic: Claude-3.5-Sonnet; Forward/executor: GPT-4o-mini | ~+9pp vs. zero-shot GPT-4o baseline; matches best few-shot CoT | Source materials describe the comparison baseline as "zero-shot GPT-4o" while the forward/execution model is GPT-4o-mini; reported as-is |
| PromptBreeder | GSM8K + SVAMP + MultiArith + AddSub + AQuA + ASDiv (mixed) | Co-evolved task-prompt and mutation-prompt populations, binary-tournament selection | N (fitness-only selection) | PaLM 2-L | Outperforms hand-engineered prompts and Auto-CoT on most arithmetic benchmarks (task-specific % not reported in reviewed materials) | Qualitative claim only for GSM8K specifically |
| MIPROv2 / DSPy | 7,473 train capped at 200 / 10% holdout val / 1,319 test | Bootstrap demonstrations -> LLM instruction proposal -> Bayesian (Optuna TPE) search | N (metric-driven Bayesian search, no raw failure text shown to the proposer) | GPT-4o-mini (default), Llama-3.1-8B, Gemini 1.5 Flash | Not reported (split/metric convention only) | Test set explicitly untouched by the 90/10 train/val convention |
| PE2 | 100 train / 300 test | Meta-meta-prompt self-optimization (GPT-4 optimizing GPT-4) | Partial (error-analysis instructions embedded in the meta-meta-prompt) | Primary: text-davinci-003; transfer: GPT-3.5, Mistral-7B, Yi-6B | Prompts optimized for text-davinci-003 transfer poorly to other models (specific % not reported) | Headline finding is about cross-model transfer, not absolute accuracy |
| PromptWizard (arithmetic ablation, zero-shot, GPT-3.5-Turbo) | 25 training examples used for optimization / full test | Mutate -> score -> critique -> synthesize instruction, plus example selection/synthesis and CoT/persona passes | Y (failed examples critiqued directly; positive examples also shown) | Optimizer/solver: GPT-3.5-Turbo | InstructZero 74.2 / Instinct 74.5 / APO 25.7 / PromptAgent 68.8 / DSPy 78.2 / **PromptWizard 90.0** | Comparison table reproduced from the PromptWizard paper's own arithmetic-reasoning results |
| FDPO (this repo), one-liner seed, validation-gated | 60 train / 59-ish test-scale batches, 3 seeds | Single whole-prompt rewrite from raw train failures + gold examples | Y (question + solver's wrong output + reference answer) | Solver: gpt-4o-mini; Optimizer: gpt-4.1 | 94-96% -> 94-96% (mean **+0.3pp**, range -1.0 to +1.0pp, 3 seeds) | Near-ceiling from the one-liner seed already; little headroom |
| FDPO (this repo), standardized 3-seed run | 120 train / 300 test | Single whole-prompt rewrite, validation-gated best-of-3-round selection | Y (same as above) | Solver: gpt-4o-mini; Optimizer: gpt-4.1 | 93.8% -> 93.0% (mean **-0.8pp**, 3 seeds) | Ceiling/downside regime; recorded net regression, not a false zero |

### 1.2 Small arithmetic transfer set (MultiArith, SVAMP, AddSub, ASDiv)

| Paper / Method | Train / Test (scale) | Mechanism | Failure Signal to Optimizer? | LLM(s) Used | Results (Before -> After) | Notes |
|---|---|---|---|---|---|---|
| APE (MultiArith only) | GSM8K-discovered trigger, transferred zero-shot | Prompt transfer, no re-optimization on MultiArith itself | N | text-davinci-002 | Not reported (transfer-evaluation only) | Used to test whether the GSM8K-discovered CoT trigger generalizes |
| PromptBreeder (all four) | Task-specific train/fitness sets, sizes not captured | Co-evolved task/mutation-prompt populations | N | PaLM 2-L | Outperforms hand-engineered + Auto-CoT baselines (task-specific % not reported) | Same qualitative claim as its GSM8K row |
| PromptWizard, SVAMP (zero-shot, GPT-3.5-Turbo) | 25 training examples / full test | Mutate/score/critique/synthesize + example synthesis + CoT/persona | Y | GPT-3.5-Turbo | InstructZero 79.5 / Instinct 81.0 / APO 75.2 / PromptAgent 78.7 / DSPy 77.0 / **PromptWizard 82.3** | From the same PromptWizard arithmetic comparison table as the GSM8K row above |

### 1.3 AQuA-RAT

| Paper / Method | Train / Test (scale) | Mechanism | Failure Signal to Optimizer? | LLM(s) Used | Results (Before -> After) | Notes |
|---|---|---|---|---|---|---|
| OPRO | 97,467 train / 254 test (full corpus) | Trajectory-based LLM-as-optimizer | N | PaLM 2-L / GPT-3.5 / GPT-4 (optimizer); PaLM 2-L / text-bison (scorer) | Not reported in reviewed materials | Listed as a dataset used, no isolated AQuA-RAT number captured |
| PE2 | 97,467 / 254 (full corpus) | Meta-meta-prompt self-optimization | Partial | text-davinci-003 (primary), GPT-3.5/Mistral-7B/Yi-6B (transfer) | Not reported in reviewed materials | Same caveat as OPRO row |
| PromptWizard (zero-shot, GPT-3.5-Turbo) | 25 training examples / full test | Mutate/score/critique/synthesize + example work + CoT/persona | Y | GPT-3.5-Turbo | InstructZero 54.3 / Instinct 54.7 / APO 20.1 / PromptAgent 56.7 / DSPy 55.1 / **PromptWizard 58.2** | From the PromptWizard arithmetic comparison table |

### 1.4 MATH500

| Paper / Method | Train / Test (scale) | Mechanism | Failure Signal to Optimizer? | LLM(s) Used | Results (Before -> After) | Notes |
|---|---|---|---|---|---|---|
| "Knowing How to Edit" (evaluation-instructed optimization) | 0 train / 200 test (fully held out) | Execution-free evaluator predicts prompt quality; structured critique instructs the optimizer which aspect to fix | Y (structured critique derived from evaluator judgments, not raw solver traces) | Not captured precisely in reviewed materials | Not reported (accuracy not captured; the paper's headline claim is evaluator compute efficiency, ~10% of full-execution cost) | Zero-training-example generalization test, deliberately held out |

### 1.5 AIME-2025 (GEPA)

Train pool = AIME 2022-2024 (90 problems, split roughly evenly for
training/validation); test = AIME-2025 (30 problems, 5 runs each = 150
generations).

| Paper / Method | Model | Mechanism | Failure Signal to Optimizer? | Results (Before -> After) |
|---|---|---|---|---|
| Baseline (no optimization) | Qwen3-8B | n/a | n/a | 27.33 |
| GRPO | Qwen3-8B | RL policy-gradient weight update (24,000 rollouts) | N (scalar reward, not a prompt rewrite) | 27.33 -> 38.00 |
| MIPROv2 | Qwen3-8B | Bayesian search over instructions + demos | N | 27.33 -> 20.00 (regression vs. baseline) |
| GEPA | Qwen3-8B | Reflective mutation + Pareto candidate selection | Y (full trace + evaluator feedback) | 27.33 -> 32.00 |
| GEPA+Merge | Qwen3-8B | GEPA plus system-aware crossover | Y | 27.33 -> 32.00 (tied with GEPA; merge added no further gain here) |
| Baseline (no optimization) | GPT-4.1 Mini | n/a | n/a | 49.33 |
| Trace (OptoPrime) | GPT-4.1 Mini | Computation-graph textual optimization | Y | 49.33 -> 45.33 (regression) |
| MIPROv2-No-Demos | GPT-4.1 Mini | Instruction-only Bayesian search | N | 49.33 -> 48.67 |
| MIPROv2 | GPT-4.1 Mini | Joint instruction + demo Bayesian search | N | 49.33 -> 51.33 |
| TextGrad | GPT-4.1 Mini | Graph-wide textual backpropagation | Y | 49.33 -> 46.67 (regression) |
| GEPA | GPT-4.1 Mini | Reflective mutation + Pareto selection | Y | 49.33 -> 59.33 |
| GEPA+Merge | GPT-4.1 Mini | GEPA plus system-aware crossover | Y | 49.33 -> 59.33 (tied with GEPA) |
| GEPA-Qwen-Opt (cross-model transfer) | Optimized on Qwen3-8B, evaluated unchanged on GPT-4.1 Mini | Same GEPA mechanism, no re-optimization for the target model | Y (at optimization time only) | 52.67 on GPT-4.1 Mini (vs. its own 49.33 baseline) |

### 1.6 LiveBench-Math (GEPA)

368 shuffled questions split roughly evenly into train/val/test.

| Paper / Method | Model | Results (Before -> After) |
|---|---|---|
| Baseline | Qwen3-8B | 48.70 |
| GRPO | Qwen3-8B | 48.70 -> 51.26 |
| MIPROv2 | Qwen3-8B | 48.70 -> 46.60 (regression) |
| GEPA | Qwen3-8B | 48.70 -> 51.95 |
| GEPA+Merge | Qwen3-8B | 48.70 -> 51.95 (tied) |
| Baseline | GPT-4.1 Mini | 58.20 |
| Trace (OptoPrime) | GPT-4.1 Mini | 58.20 -> 60.74 |
| MIPROv2-No-Demos | GPT-4.1 Mini | 58.20 -> 60.97 |
| MIPROv2 | GPT-4.1 Mini | 58.20 -> 61.84 |
| TextGrad | GPT-4.1 Mini | 58.20 -> 63.84 |
| GEPA | GPT-4.1 Mini | 58.20 -> 64.13 |
| GEPA+Merge | GPT-4.1 Mini | 58.20 -> 64.13 (tied) |
| GEPA-Qwen-Opt (transfer) | Optimized Qwen3-8B, evaluated on GPT-4.1 Mini | 59.31 (vs. 58.20 baseline) |

Mechanism/failure-signal columns for this table are identical to Section 1.5
(same GEPA paper, same method definitions) and are omitted here for brevity.

---

## 2. Multi-Step, Multi-Hop, and Fact-Verification Reasoning

### 2.1 BIG-Bench Hard (BBH)

| Paper / Method | Train / Test (scale) | Mechanism | Failure Signal to Optimizer? | LLM(s) Used | Results (Before -> After) | Notes |
|---|---|---|---|---|---|---|
| Baseline ("Let's think step by step.") | n/a | Fixed zero-shot CoT trigger | n/a | n/a | 71.49 (aggregate over 23 subtasks) | Reference point every later row compares against |
| APE | Task-specific, ~250/250 per subtask | Generate-and-score, paraphrase | N | text-davinci-001/002-class | 71.49 -> 71.85 | Near-baseline |
| OPRO | ~100 train / ~200 test per subtask | Trajectory-based meta-prompt | N | PaLM 2-L / GPT-3.5 / GPT-4 (optimizer); PaLM 2-L / text-bison (scorer) | Beats zero-shot-CoT baseline by >5pp on 19 of 23 subtasks (aggregate % not reported) | Per-subtask win-count reported, not a single aggregate number |
| PromptAgent | 50 train / 200 test, 6 of the 23 subtasks | MCTS over a tree of expert-level prompts | Y (LLM-agent edits conditioned on failure samples) | Worker: GPT-3.5-turbo; Optimizer/agent: GPT-4 | ~+9pp average vs. APE/CoT baselines on its 6-subtask subset | Subset of BBH, not the full 23-task aggregate |
| EvoPrompt (GA) | Population of 10, 4 generations | Genetic-algorithm evolutionary search | N (scalar dev-set fitness only) | Alpaca-7B / GPT-3.5 | 71.49 -> 74.18 | |
| EvoPrompt (DE) | Population of 10, 4 generations | Differential-evolution evolutionary search | N | Alpaca-7B / GPT-3.5 | 71.49 -> 75.03 | Generally the more stable EvoPrompt variant |
| PromptWizard | 25 training examples per task (across 23 BBH tasks) | Mutate/score/critique/synthesize + example work + CoT/persona | Y | GPT-3.5-Turbo / GPT-4 | 71.49 -> **88.1** | Largest reported BBH aggregate gain in this table |

### 2.2 BIG-Bench Hard subset for OPRO ablations, and StrategyQA

| Paper / Method | Train / Test (scale) | Mechanism | Failure Signal to Optimizer? | LLM(s) Used | Results (Before -> After) | Notes |
|---|---|---|---|---|---|---|
| APE (StrategyQA) | 10 demonstrations / 50 test | Generate-and-score | N | text-davinci-001/002 | Not reported in reviewed materials | Listed as a used dataset only |
| OPRO (StrategyQA) | 2,290 train / 490 test | Trajectory-based meta-prompt | N | PaLM 2-L / GPT-3.5 / GPT-4 | Not reported in reviewed materials | |
| GLaPE (StrategyQA) | Population-based, size not captured | Textual gradient + evolutionary outer loop | Y (gradient portion sees failures) | Variant-dependent | Not reported in reviewed materials | |

### 2.3 HotpotQA

| Paper / Method | Train / Test (scale) | Mechanism | Failure Signal to Optimizer? | LLM(s) Used | Results (Before -> After) | Notes |
|---|---|---|---|---|---|---|
| DSPy (framework convention) | 500 train / 50 val / 7,405 test | BootstrapFewShot / COPRO / MIPROv2 (framework choice) | Depends on optimizer chosen (COPRO/MIPROv2: N) | GPT-4o-mini / Llama-3.1-8B / Gemini 1.5 Flash | Not reported (F1 metric, split convention only) | Metric is F1, not accuracy |
| Baseline (no optimization) | 150 train / 300 val / 300 test | n/a | n/a | Qwen3-8B | 42.33 | |
| GRPO | same split | RL policy-gradient weight update (24,000 rollouts) | N | Qwen3-8B | 42.33 -> 43.33 | |
| MIPROv2 | same split | Bayesian search over instructions + demos | N | Qwen3-8B | 42.33 -> 55.33 | |
| GEPA | same split | Reflective mutation + Pareto selection | Y | Qwen3-8B | 42.33 -> 62.33 | |
| GEPA+Merge | same split | GEPA + system-aware crossover | Y | Qwen3-8B | 42.33 -> 64.33 | Best result in the Qwen3-8B condition |
| Baseline (no optimization) | same split | n/a | n/a | GPT-4.1 Mini | 38.00 | |
| Trace (OptoPrime) | same split | Computation-graph textual optimization | Y | GPT-4.1 Mini | 38.00 -> 60.33 | |
| MIPROv2-No-Demos | same split | Instruction-only Bayesian search | N | GPT-4.1 Mini | 38.00 -> 38.00 (no change) | |
| MIPROv2 | same split | Joint instruction + demo Bayesian search | N | GPT-4.1 Mini | 38.00 -> 58.00 | |
| TextGrad | same split | Graph-wide textual backpropagation | Y | GPT-4.1 Mini | 38.00 -> 62.33 | |
| GEPA | same split | Reflective mutation + Pareto selection | Y | GPT-4.1 Mini | 38.00 -> 69.00 | Best single-model result reported for GEPA in this table |
| GEPA+Merge | same split | GEPA + system-aware crossover | Y | GPT-4.1 Mini | 38.00 -> 65.67 | Merge underperforms plain GEPA here |
| GEPA-Qwen-Opt (transfer) | optimized on Qwen3-8B, evaluated unchanged | Same GEPA mechanism, no re-optimization for target model | Y (at optimization time) | Evaluated on GPT-4.1 Mini | 65.67 (vs. its own 38.00 baseline) | Largest reported cross-model transfer gain in the GEPA paper |

### 2.4 HoVer (multi-hop fact verification)

150 train / 300 val / 300 test for all rows below.

| Paper / Method | Mechanism | Failure Signal to Optimizer? | LLM(s) Used | Results (Before -> After) |
|---|---|---|---|---|
| Baseline | n/a | n/a | Qwen3-8B | 35.33 |
| GRPO | RL weight update | N | Qwen3-8B | 35.33 -> 38.67 |
| MIPROv2 | Bayesian search | N | Qwen3-8B | 35.33 -> 47.33 |
| GEPA | Reflective mutation + Pareto selection | Y | Qwen3-8B | 35.33 -> 52.33 |
| GEPA+Merge | GEPA + crossover | Y | Qwen3-8B | 35.33 -> 51.67 |
| Baseline | n/a | n/a | GPT-4.1 Mini | 46.33 |
| Trace (OptoPrime) | Textual graph optimization | Y | GPT-4.1 Mini | 46.33 -> 46.00 (regression) |
| MIPROv2-No-Demos | Instruction-only search | N | GPT-4.1 Mini | 46.33 -> 51.33 |
| MIPROv2 | Joint instruction + demo search | N | GPT-4.1 Mini | 46.33 -> 48.33 |
| TextGrad | Graph-wide backpropagation | Y | GPT-4.1 Mini | 46.33 -> 47.67 |
| GEPA | Reflective mutation + Pareto selection | Y | GPT-4.1 Mini | 46.33 -> 51.67 |
| GEPA+Merge | GEPA + crossover | Y | GPT-4.1 Mini | 46.33 -> **56.67** | 
| GEPA-Qwen-Opt (transfer) | Same mechanism, no target re-optimization | Y (at optimization time) | Evaluated on GPT-4.1 Mini | 54.67 (vs. its own 46.33 baseline) |

---

## 3. Knowledge and Multiple-Choice QA

### 3.1 MMLU

| Paper / Method | Train / Test (scale) | Mechanism | Failure Signal to Optimizer? | LLM(s) Used | Results (Before -> After) | Notes |
|---|---|---|---|---|---|---|
| TextGrad (MMLU-ML subset) | 50 train / 50 val / rest test | Computation-graph textual backpropagation | Y | Claude-3.5-Sonnet (backward), GPT-4o-mini (forward) | Not reported (specific accuracy not captured in reviewed materials) | ML-subset only, not full MMLU |
| MPO (LLaMA-3-8B-Instruct) | Task-specific, not captured precisely | Section-local textual gradients + LLM de-duplication over a fixed 5-section schema | N (no failure examples shown to the critic) | LLaMA-3-8B-Instruct (solver + critic) | 57.21% -> 61.50% (**+4.29pp**) | MPO's own untuned/TextGrad/MPO 3-way comparison; no regression gate |
| MPO (Mistral-7B-Instruct) | Same as above | Same mechanism | N | Mistral-7B-Instruct | 53.79% -> 55.50% (**+1.71pp**) | |
| TextGrad (as run inside the MPO paper's comparison, LLaMA-3-8B) | Same MPO protocol | Graph-based textual backpropagation | Y | LLaMA-3-8B-Instruct | 57.21% -> 56.40% (**regression**, -0.81pp) | Cited by MPO as evidence that monolithic updates can be less stable than section-local ones |
| FDPO (this repo), 6-subject aggregate, GPT-4.1 optimizer | 66 test per subject, 3 seeds/subject, neutral seed prompt | Single whole-prompt rewrite from raw failures | Y (question + wrong output + reference) | Solver: gpt-4o-mini; Optimizer: gpt-4.1 | ~59.3% -> ~60.7% aggregate (**+0.4pp macro**); per-subject: college_math +5.5, philosophy +4.0, econometrics +2.0, biology +0.5, professional_law -1.0, computer_security **-8.6** | Aggregate hides large two-way churn; see the sub-table below |
| FDPO (this repo), 6-subject aggregate, GPT-5 optimizer | Same protocol, 2 seeds/subject | Same mechanism, newer optimizer model | Y | Solver: gpt-4o-mini; Optimizer: gpt-5 | ~0.0pp macro; per-subject: college_math +1.5, philosophy +3.8, professional_law +2.7, biology 0.0, computer_security -1.5, econometrics **-6.8** | Confirms the per-subject heterogeneity is not specific to one optimizer model |

**MMLU sub-table: FDPO per-subject churn detail (both optimizers), for reference**

| Subject | GPT-4.1 optimizer mean delta (3 seeds) | GPT-5 optimizer mean delta (2 seeds) | Regime |
|---|---:|---:|---|
| College mathematics | +5.5pp | +1.5pp | Reasoning-heavy, headroom present |
| Econometrics | +2.0pp | -6.8pp | Highly protocol-sensitive |
| High-school biology | +0.5pp | 0.0pp | Near-ceiling / neutral |
| Philosophy | +4.0pp | +3.8pp | Most repeatable positive subject |
| Computer security | -8.6pp | -1.5pp | Recall-heavy, near-ceiling, downside |
| Professional law | -1.0pp | +2.7pp | Sign flips across optimizer/protocol |

### 3.2 ARC-Challenge

| Paper / Method | Train / Test (scale) | Mechanism | Failure Signal to Optimizer? | LLM(s) Used | Results (Before -> After) | Notes |
|---|---|---|---|---|---|---|
| MPO (LLaMA-3-8B-Instruct) | Official split (1,119 / 1,172) | Section-local textual gradients + de-duplication | N | LLaMA-3-8B-Instruct | 75.00% -> 79.10% (**+4.10pp**) | |
| MPO (Mistral-7B-Instruct) | Same | Same mechanism | N | Mistral-7B-Instruct | 70.73% -> 73.04% (**+2.31pp**) | |
| FDPO (this repo) | Toy n=10 (gpt-4.1) / 300 zero-shot (gpt-4o-mini) | n/a - optimization not run | n/a | gpt-4.1 (toy) / gpt-4o-mini (zero-shot baseline) | 100% (toy, gpt-4.1) / ~95.0% zero-shot (gpt-4o-mini); no optimized-final number | Deliberately not optimized - acknowledged ceiling effect on this solver; recommended re-run on a weaker open solver in the finish plan |

### 3.3 GPQA Diamond

| Paper / Method | Train / Test (scale) | Mechanism | Failure Signal to Optimizer? | LLM(s) Used | Results (Before -> After) | Notes |
|---|---|---|---|---|---|---|
| TextGrad | Full test set | Graph-wide textual backpropagation | Y | Claude-3.5-Sonnet (backward), GPT-4o-mini (forward) | Not reported in reviewed materials | One of TextGrad's six reported task settings |
| ETGPO | Included in its taxonomy-guided validation suite | Error-taxonomy clustering -> per-category guidance -> single rewrite | Y (clustered failures) | Not captured precisely in reviewed materials | Not reported (qualitative: "more stable than GEPA, comparable to MIPROv2 heavy mode at lower compute") | |
| "Knowing How to Edit" | 100 train / 100 test (seen task) | Execution-free evaluator + evaluation-instructed optimization | Y (structured critique from evaluator) | Not captured precisely in reviewed materials | Not reported (efficiency claim only: ~10% of full-execution evaluator cost) | |

### 3.4 MedQA

| Paper / Method | Train / Test (scale) | Mechanism | Failure Signal to Optimizer? | LLM(s) Used | Results (Before -> After) | Notes |
|---|---|---|---|---|---|---|
| DSPy / MIPROv2 | 100 train / 50 val / 1,273 test | Bootstrap + instruction proposal + Bayesian search | N | GPT-4o-mini (default) | Not reported in reviewed materials | |
| "Knowing How to Edit" | 0 train / 200 test (fully held out) | Execution-free evaluator + evaluation-instructed optimization | Y (structured critique) | Not captured precisely in reviewed materials | Not reported (generalization test, not a headline accuracy claim) | Zero-shot generalization arm, like its MATH500 row |

---

## 4. Text Classification (Sentiment, Topic, Subjectivity)

All rows in this section come from the same comparison table (EvoPrompt
paper), which reports manual-instruction (MI), natural-instructions (NI),
PromptSource, APE, APO/ProTeGi, and both EvoPrompt variants side by side on
Alpaca-7B execution; standard deviations across 3 seeds are in parentheses
where the source reports them.

### 4.1 SST-2

| Paper / Method | Mechanism | Failure Signal to Optimizer? | Results (Accuracy) |
|---|---|---|---|
| Manual Instruction (MI) | Human-written baseline | n/a | 93.68 |
| Natural Instructions (NI) | Crowd-sourced instruction template | n/a | 92.86 |
| PromptSource | Human-composed prompt repository | n/a | 93.03 |
| APE | Generate-and-score | N | 93.45 (0.14) |
| APO / ProTeGi | Textual-gradient beam search | Y | 93.87 (0.39) |
| EvoPrompt (GA) | Genetic-algorithm population search | N | **95.13 (0.21)** |
| EvoPrompt (DE) | Differential-evolution population search | N | 94.75 (0.21) |

### 4.2 SST-5

| Paper / Method | Mechanism | Failure Signal to Optimizer? | Results (Accuracy) |
|---|---|---|---|
| Manual Instruction (MI) | Human-written baseline | n/a | 42.90 |
| Natural Instructions (NI) | Crowd-sourced instruction template | n/a | 48.64 |
| APE | Generate-and-score | N | 46.32 (0.49) |
| EvoPrompt (GA) | Genetic-algorithm population search | N | 49.91 (0.61) |
| EvoPrompt (DE) | Differential-evolution population search | N | **49.89 (1.73)** (high seed variance) |

### 4.3 AG's News

| Paper / Method | Mechanism | Failure Signal to Optimizer? | Results (Accuracy) |
|---|---|---|---|
| Manual Instruction (MI) | Human-written baseline | n/a | 70.63 |
| Natural Instructions (NI) | Crowd-sourced instruction template | n/a | 48.89 |
| PromptSource | Human-composed prompt repository | n/a | 45.43 |
| APE | Generate-and-score | N | 71.76 (2.81) |
| EvoPrompt (GA) | Genetic-algorithm population search | N | 72.81 (0.61) |
| EvoPrompt (DE) | Differential-evolution population search | N | **73.82 (0.35)** |

### 4.4 TREC

| Paper / Method | Mechanism | Failure Signal to Optimizer? | Results (Accuracy) |
|---|---|---|---|
| Manual Instruction (MI) | Human-written baseline | n/a | 50.60 |
| Natural Instructions (NI) | Crowd-sourced instruction template | n/a | 55.00 |
| PromptSource | Human-composed prompt repository | n/a | 36.20 |
| APE | Generate-and-score | N | 58.73 (1.37) |
| EvoPrompt (GA) | Genetic-algorithm population search | N | **64.00 (0.16)** |
| EvoPrompt (DE) | Differential-evolution population search | N | 63.73 (1.54) |

### 4.5 Subj

| Paper / Method | Mechanism | Failure Signal to Optimizer? | Results (Accuracy) |
|---|---|---|---|
| Manual Instruction (MI) | Human-written baseline | n/a | 49.75 |
| Natural Instructions (NI) | Crowd-sourced instruction template | n/a | 52.55 |
| APE | Generate-and-score | N | 64.18 (0.59) |
| APO / ProTeGi | Textual-gradient beam search | Y | 70.55 (1.02) |
| EvoPrompt (GA) | Genetic-algorithm population search | N | 70.55 (2.58) |
| EvoPrompt (DE) | Differential-evolution population search | N | **75.55 (2.26)** |

### 4.6 CR (customer reviews)

| Paper / Method | Mechanism | Failure Signal to Optimizer? | Results (Accuracy) |
|---|---|---|---|
| Manual Instruction (MI) | Human-written baseline | n/a | 91.40 |
| Natural Instructions (NI) | Crowd-sourced instruction template | n/a | 90.90 |
| APE | Generate-and-score | N | 91.13 (0.45) |
| APO / ProTeGi | Textual-gradient beam search | Y | 91.20 (0.04) |
| EvoPrompt (GA) | Genetic-algorithm population search | N | 91.27 (0.06) |
| EvoPrompt (DE) | Differential-evolution population search | N | **91.40 (0.04)** |

### 4.7 MR (movie reviews)

| Paper / Method | Mechanism | Failure Signal to Optimizer? | Results (Accuracy) |
|---|---|---|---|
| Manual Instruction (MI) | Human-written baseline | n/a | 88.75 |
| Natural Instructions (NI) | Crowd-sourced instruction template | n/a | 89.60 |
| APE | Generate-and-score | N | 89.98 (0.29) |
| APO / ProTeGi | Textual-gradient beam search | Y | 89.85 (0.35) |
| EvoPrompt (GA) | Genetic-algorithm population search | N | 90.07 (0.25) |
| EvoPrompt (DE) | Differential-evolution population search | N | **90.22 (0.09)** |

---

## 5. Safety and Moderation Classification (ProTeGi suite)

All four rows below are from ProTeGi's own paper; per-dataset before/after
splits were not individually captured in the reviewed materials, only the
aggregate improvement statement and each dataset's split size, so the
Results column intentionally repeats the paper's aggregate claim rather than
inventing a per-dataset number.

| Dataset | Train / Test (scale) | Mechanism | Failure Signal to Optimizer? | LLM(s) Used | Results (aggregate, ProTeGi paper) | Notes |
|---|---|---|---|---|---|---|
| Ethos (hate speech) | 750 / 200 | Textual-gradient critique + beam search (width 4, depth 6) | Y (batch of 64 failures per gradient step) | GPT-3.5-turbo (gradient generator + scorer) | Up to +31% F1 vs. initial prompt; +4-8% vs. Monte-Carlo/RL baselines (aggregate across all 4 datasets, 3-run average) | Per-dataset breakdown not captured in reviewed materials |
| Liar (fake news) | ~3,681 / 461 (ProTeGi-specific subsample, per this repo's prior notes) | Same mechanism | Y | GPT-3.5-turbo | Same aggregate claim as above | Caveat: a separate note in this repository's own prior research lists the full LIAR corpus as 10,269/1,267; the ProTeGi-specific subsample size has not been re-verified against the primary source in this session |
| Jailbreak (custom safety set) | Custom / 200 | Same mechanism | Y | GPT-3.5-turbo | Same aggregate claim as above | |
| Sarcasm | 800 / 200 | Same mechanism | Y | GPT-3.5-turbo | Same aggregate claim as above | |

---

## 6. Legal and Domain-Specific Rule Application

### 6.1 LegalBench Hearsay

| Paper / Method | Train / Test (scale) | Mechanism | Failure Signal to Optimizer? | LLM(s) Used | Results (Before -> After) | Notes |
|---|---|---|---|---|---|---|
| Trace2Policy / EISR (public LegalBench probe) | 30-case iteration pool / 64-case "held-out" test | Cluster errors into MISSING/WRONG/CONFLICT, propose patches, regression gate (>2pp drop discarded), best-snapshot rollback | Y (clustered failure batches) | Claude Haiku 4.5 (one of six solver models tested) | 79.7% (B1b baseline) -> 93.8% (v_EISR, 2 rounds) (**+14.1pp**) | **Caveat:** this repository's replication found the paper's own Appendix states one round was diagnosed partly from the nominally held-out set's own errors, meaning the test set was not fully disjoint from refinement for this specific public probe |
| FDPO (this repo), Trace2Policy-protocol replication, sealed test | 30 train / 64 test (stratified, seed 42) | Single whole-prompt rewrite, 2 rounds, no accept-margin leniency | Y (question + wrong output + reference) | Solver: Claude Haiku 4.5; Optimizer: gpt-5 | 68.8% -> 73.4% (**+4.7pp**, honest, sealed test, 1 seed) | Directly comparable protocol to the Trace2Policy row above, using a genuinely sealed test |
| FDPO (this repo), oracle/leak diagnostic | Sealed 64-item test pool deliberately used as the mining pool | Same mechanism, deliberately exposed to the test set | Y | Same as above | 68.8% -> **95.3%** (+26.6pp) | **INVALID as a result - diagnostic only.** Demonstrates that test exposure alone can match or exceed a human-curated gain; must never be cited as a real FDPO accuracy number |
| FDPO (this repo), validation-gated 3-round run, one-liner seed | 40 train (26 mining / 14 validation) / 59 test, 3 seeds | Single whole-prompt rewrite, 3 rounds, validation-selected best, lenient accept | Y | Solver: gpt-4o-mini; Optimizer: gpt-4.1 | 62.7% -> 71.2% (**+8.5pp**, all 3 seeds identical delta) | Strongest older standardized result; small reused test set |
| FDPO (this repo), GPT-5 optimizer, permissive gate | 40 train / 59 test, 2 seeds | Single whole-prompt rewrite, 3 rounds, `accept_margin=1.0` (ships almost anything) | Y | Solver: gpt-4o-mini; Optimizer: gpt-5 | 66.1% -> 55.9% (**-10.2pp**) | Direct counterexample to any "the optimizer always helps" claim |
| FDPO (this repo), earlier "chained" v1/v2-era run | 3 seeds, older mechanism version | Multi-round judge-attributed section rewrite with a regression gate (pre-`simple_fdpo`) | Y (judge-routed per-section failures) | Solver: gpt-4o-mini; Optimizer: gpt-4.1 | 68.9% -> 66.7% (**-2.3pp**) | Uses the retired v2 mechanism, kept for historical comparison only |

### 6.2 LegalBench Contract NLI

| Paper / Method | Train / Test (scale) | Mechanism | Failure Signal to Optimizer? | LLM(s) Used | Results (Before -> After) | Notes |
|---|---|---|---|---|---|---|
| Trace2Policy / EISR | Not captured precisely in reviewed materials | Clustered-error refinement + regression gate | Y | One of six solver models (per its multi-model evaluation) | Not reported in reviewed materials | Listed as one of the paper's evaluation datasets alongside hearsay |
| FDPO (this repo) | Dataset loader and seed prompt present (`legalbench_contract_nli`) | n/a - no completed optimization run yet | n/a | n/a | No result yet | Recommended addition in the finish plan's Phase C task matrix |

### 6.3 LegalBench Definition Classification

| Paper / Method | Train / Test (scale) | Mechanism | Failure Signal to Optimizer? | LLM(s) Used | Results (Before -> After) | Notes |
|---|---|---|---|---|---|---|
| DSPy / MIPROv2 | 80-100 train / 40 val / 200 test | Bootstrap + instruction proposal + Bayesian search | N | GPT-4o-mini (default) | Not reported in reviewed materials | |
| "Knowing How to Edit" | 100 train / 100 test (seen task) | Execution-free evaluator + evaluation-instructed optimization | Y | Not captured precisely in reviewed materials | Not reported in reviewed materials | |

### 6.4 Other LegalBench tasks (name-only mentions)

| Dataset | Used by | Notes |
|---|---|---|
| LegalBench Unfair ToS | Trace2Policy / EISR | Listed as an evaluation dataset; no specific numbers captured in reviewed materials |
| Broader LegalBench (162-task benchmark) | "Knowing How to Edit" (general reference), DSPy line of work | Cited as the source benchmark family; no aggregate 162-task number captured |

---

## 7. Code Generation

### 7.1 HumanEval

| Paper / Method | Train / Test (scale) | Mechanism | Failure Signal to Optimizer? | LLM(s) Used | Results (Before -> After) | Notes |
|---|---|---|---|---|---|---|
| TextGrad | 0 train / 164 test (standard split) | Computation-graph textual backpropagation | Y | Claude-3.5-Sonnet (backward), GPT-4o-mini (forward) | Not reported (Pass@1 metric; specific number not captured in reviewed materials) | One of TextGrad's six reported task settings |

---

## 8. Summarization and Text Simplification

### 8.1 SAMSum (dialogue summarization, ROUGE-1/2/L)

| Paper / Method | Model | Results (ROUGE-1 / ROUGE-2 / ROUGE-L) |
|---|---|---|
| Manual Instruction (MI) | Alpaca-7B | 35.92 / 11.16 / 31.67 |
| APE | Alpaca-7B | 35.44 (0.79) / 10.60 (0.38) / 31.80 (0.50) |
| EvoPrompt (GA) | Alpaca-7B | 38.46 (1.45) / 13.36 (0.75) / 34.20 (1.40) |
| EvoPrompt (DE) | Alpaca-7B | **39.46 (0.51) / 13.93 (0.33) / 35.49 (0.56)** |
| Manual Instruction (MI) | GPT-3.5 | 43.95 / 17.11 / 39.09 |
| APE | GPT-3.5 | 43.43 / 16.72 / 38.25 |
| EvoPrompt (GA) | GPT-3.5 | 45.22 / 18.52 / 41.06 |
| EvoPrompt (DE) | GPT-3.5 | **46.49 / 19.49 / 41.96** |

Mechanism and failure-signal columns are identical to Section 4's EvoPrompt
rows (GA/DE population search, no raw failures shown; APE is
generate-and-score) and are omitted here for brevity.

### 8.2 ASSET (text simplification, SARI)

| Paper / Method | Model | Results (SARI) |
|---|---|---|
| Manual Instruction (MI) | Alpaca-7B | 43.03 |
| APE | Alpaca-7B | 45.90 (0.09) |
| EvoPrompt (GA) | Alpaca-7B | 46.43 (0.19) |
| EvoPrompt (DE) | Alpaca-7B | 46.21 (0.27) |
| Manual Instruction (MI) | GPT-3.5 | 43.80 |
| APE | GPT-3.5 | 46.71 |
| EvoPrompt (GA) | GPT-3.5 | **47.36** |
| EvoPrompt (DE) | GPT-3.5 | 47.40 |

---

## 9. Instruction Induction and BBII (Big-Bench Instruction Induction)

These are meta-task benchmarks (roughly 19-24 short sub-tasks like antonyms,
cause-and-effect, word-sorting) used to test whether an optimizer can
recover the instruction that explains a handful of input-output examples.
Individual sub-task numbers are not reproduced here; win-count summaries are
used instead, matching how the source papers themselves report the
aggregate.

| Paper / Method | Train / Test (scale) | Mechanism | Failure Signal to Optimizer? | LLM(s) Used | Results (win-count) | Notes |
|---|---|---|---|---|---|---|
| APE | 10 demonstrations / 50 test, per sub-task | Generate-and-score, iterative paraphrase | N | text-davinci-001/002 | Established the 24-task Instruction Induction benchmark; per-task comparisons, no single aggregate isolated here | |
| EvoPrompt (3 named sub-tasks: Antonyms, Cause-Selection, Active-to-Passive) | 10 demonstrations / 50 test per sub-task | Evolutionary GA/DE population search | N | Alpaca-7B / GPT-3.5 | Included in EvoPrompt's 31-dataset average; per-sub-task numbers not isolated in reviewed materials | |
| PromptWizard, BBII zero-shot (GPT-3.5-Turbo) | 25 training examples per task, 19 BBII tasks | Mutate/score/critique/synthesize + example work | Y | GPT-3.5-Turbo | **13 / 19** best-performing tasks, vs. Instinct's 8/19 | |
| PromptWizard, BBII one-shot (GPT-3.5-Turbo) | Same, plus one optimized in-context example | Same mechanism plus example optimization | Y | GPT-3.5-Turbo | **16 / 19** best-performing tasks, vs. Instinct's 7/19 | |
| PromptWizard, BBII (GPT-4 base model) | Same 19 tasks | Same mechanism | Y | GPT-4 | **15 / 19** best-performing tasks (79%), vs. Instinct's 6/19 (31%) | |

---

## 10. Instruction-Following and Agentic Delegation Benchmarks (GEPA)

### 10.1 IFBench

150 train / 300 val / 294 test for every row below.

| Paper / Method | Model | Mechanism | Failure Signal to Optimizer? | Results (Before -> After) |
|---|---|---|---|---|
| Baseline | Qwen3-8B | n/a | n/a | 36.90 |
| GRPO | Qwen3-8B | RL weight update | N | 36.90 -> 35.88 (regression) |
| MIPROv2 | Qwen3-8B | Bayesian search | N | 36.90 -> 36.22 (regression) |
| GEPA | Qwen3-8B | Reflective mutation + Pareto selection | Y | 36.90 -> 38.61 |
| GEPA+Merge | Qwen3-8B | GEPA + crossover | Y | 36.90 -> 28.23 (**merge sharply hurts here**) |
| Baseline | GPT-4.1 Mini | n/a | n/a | 47.79 |
| Trace (OptoPrime) | GPT-4.1 Mini | Textual graph optimization | Y | 47.79 -> 51.19 |
| MIPROv2-No-Demos | GPT-4.1 Mini | Instruction-only search | N | 47.79 -> 52.04 |
| MIPROv2 | GPT-4.1 Mini | Joint instruction + demo search | N | 47.79 -> 49.15 |
| TextGrad | GPT-4.1 Mini | Graph-wide backpropagation | Y | 47.79 -> 48.64 |
| GEPA | GPT-4.1 Mini | Reflective mutation + Pareto selection | Y | 47.79 -> 52.72 |
| GEPA+Merge | GPT-4.1 Mini | GEPA + crossover | Y | 47.79 -> **55.95** |
| GEPA-Qwen-Opt (transfer) | Optimized on Qwen3-8B, evaluated on GPT-4.1 Mini | Same mechanism, no target re-optimization | Y (at optimization time) | 49.83 (vs. its own 47.79 baseline) |

### 10.2 PUPA (privacy-aware delegation)

111 train / 111 val / 221 test for every row below.

| Paper / Method | Model | Mechanism | Failure Signal to Optimizer? | Results (Before -> After) |
|---|---|---|---|---|
| Baseline | Qwen3-8B | n/a | n/a | 80.82 |
| GRPO | Qwen3-8B | RL weight update | N | 80.82 -> 86.66 |
| MIPROv2 | Qwen3-8B | Bayesian search | N | 80.82 -> 81.55 |
| GEPA | Qwen3-8B | Reflective mutation + Pareto selection | Y | 80.82 -> **91.85** |
| GEPA+Merge | Qwen3-8B | GEPA + crossover | Y | 80.82 -> 86.26 (below plain GEPA) |
| Baseline | GPT-4.1 Mini | n/a | n/a | 78.57 |
| Trace (OptoPrime) | GPT-4.1 Mini | Textual graph optimization | Y | 78.57 -> 74.18 (regression) |
| MIPROv2-No-Demos | GPT-4.1 Mini | Instruction-only search | N | 78.57 -> 91.85 |
| MIPROv2 | GPT-4.1 Mini | Joint instruction + demo search | N | 78.57 -> 83.37 |
| TextGrad | GPT-4.1 Mini | Graph-wide backpropagation | Y | 78.57 -> 85.68 |
| GEPA | GPT-4.1 Mini | Reflective mutation + Pareto selection | Y | 78.57 -> 94.47 |
| GEPA+Merge | GPT-4.1 Mini | GEPA + crossover | Y | 78.57 -> **96.46** |
| GEPA-Qwen-Opt (transfer) | Optimized on Qwen3-8B, evaluated on GPT-4.1 Mini | Same mechanism, no target re-optimization | Y (at optimization time) | 90.05 (vs. its own 78.57 baseline) |

---

## 11. Human-Preference and Rewriter-Training Corpora

These are not held-out accuracy benchmarks in the usual sense; they are the
corpora used to fine-tune or evaluate rewriter models via preference/quality
judgments, so the "Results" column reports what was actually captured
(usually qualitative) rather than a fabricated accuracy number.

| Dataset(s) | Used by | Train / Test (scale) | Mechanism | Failure Signal to Optimizer? | LLM(s) Used | Results | Notes |
|---|---|---|---|---|---|---|---|
| Anthropic HH, OpenAssistant | BPO | Preference pairs mined from large-scale data, size not captured | SFT-trained universal rewriter model | Indirectly, via mined (bad-prompt, good-prompt, quality) triples | Rewriter: Llama-2-7B; downstream: GPT-3.5, GPT-4, Llama-2 | "Improves response quality across downstream models" (no specific win-rate captured) | Costs are amortized: one rewriter generalizes across users/tasks |
| AlpacaEval, MT-Bench | FIPO | Curated (instruction, optimized-instruction, quality-score) corpus, size not captured | SFT-trained rewriter specialized to instruction-following tasks | Indirectly, via GPT-4-filtered training triples | Rewriter: small LM; downstream: instruction-tuned LLMs | Not reported (qualitative "gains on AlpacaEval/MT-Bench" only) | |
| GLUE / SuperGLUE family | PRewrite | Standard splits | RL (PPO)-trained rewriter model | N (reward is a downstream accuracy delta, not a shown failure trace) | Rewriter: T5-base / Llama-3-8B; downstream: task model | Not reported (specific accuracy delta not captured) | Rewriter generalizes to unseen base prompts without further training, unlike per-prompt online loops |

---

## 12. Production and Business-Process Streams (Trace2Policy)

| Dataset | Train / Test (scale) | Mechanism | Failure Signal to Optimizer? | LLM(s) Used | Results (Before -> After) | Notes |
|---|---|---|---|---|---|---|
| Logistics audit (proprietary) | 3,349 cases over 22 days | Clustered-error refinement (MISSING/WRONG/CONFLICT) + regression gate + best-snapshot rollback | Y | GLM-5, Kimi-K2.5, Qwen3.5-plus, MiniMax-M2.5, Claude Opus 4.6, Claude Haiku 4.5 (6-model average) | 70.3% (B1b zero-shot) -> 73.3% (B5 few-shot) -> 69.2% (v1 unrefined rules) -> **78.9%** (v8, EISR-refined) -> **79.6%** (compiled Python execution of the same rules) | Action-classification accuracy, averaged across all 6 solver models |
| BPIC 2012 (business-process event log) | Standard event-log split | Same clustered-error refinement mechanism | Y | Not captured precisely in reviewed materials | Not reported in reviewed materials | Listed as one of the paper's evaluation datasets |

---

## 13. Scientific, Molecular, and Clinical Case Studies (TextGrad)

| Dataset | Train / Test (scale) | Mechanism | Failure Signal to Optimizer? | LLM(s) Used | Results | Notes |
|---|---|---|---|---|---|---|
| DOCKSTRING (58 molecular targets) | All 58 targets | Computation-graph textual backpropagation | Y | Claude-3.5-Sonnet (backward), GPT-4o-mini (forward) | Not reported (metric is binding affinity; specific values not captured in reviewed materials) | Molecule-generation case study |
| Radiotherapy treatment planning | Case-based | Same mechanism | Y | Same as above | Not reported (metric is clinical-criteria satisfaction; specific values not captured) | Clinical planning case study, not a public leaderboard benchmark |

---

## 14. Named Only in the Taxonomy Survey (no primary results reviewed)

The 2025 optimization-perspective survey (arXiv:2502.11560v1) names these
datasets as illustrative examples of task categories in its taxonomy; it
runs no experiments of its own, so no before/after numbers exist to report.
Listed here only so this document's dataset coverage is complete.

| Dataset | Task category (per the survey) | Notes |
|---|---|---|
| SingleEq | Math reasoning example | Named alongside MultiArith as a math-reasoning dataset example |
| CommonsenseQA | Commonsense reasoning example | Named alongside StrategyQA |
| MS COCO | Multimodal image-text example | Image captioning/retrieval |
| LAION | Multimodal image-text example | Large-scale image-text pretraining corpus |
| Celeb-A | Multimodal image-text example | Face-attribute dataset, cited for multimodal prompting |

---

## 15. Maintenance note

When a new dataset is reviewed, add it as a new table under the matching
family section above (or create a new family section if none fits), keeping
the same seven-column layout. When a new paper reports on an existing
dataset, add a new row to that dataset's existing table rather than creating
a duplicate table.

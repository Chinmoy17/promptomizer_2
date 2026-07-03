# FDPO — Feedback-Driven Modular Prompt Optimization (Pilot)

Pilot experiments for FDPO: prompts as K semantic sections, LLM-judge failure
attribution per section, section-local rewrites, and a per-section regression
gate with rollback. See [plan.md](plan.md) for the current experiment plan and
[Docs/](Docs/) for the research proposal and literature survey.

## Quick start (Windows PowerShell; Linux identical minus `Copy-Item`)

```powershell
uv sync
Copy-Item .env.example .env    # fill in real API keys / endpoints
uv run python -m pytest
uv run python -m scripts.run_experiment --help
```

Full setup, run instructions, and the TAMU cluster handoff notes are being
written as the scaffold lands (see plan.md milestones).

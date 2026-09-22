# fdpo runner image: the orchestrator only. It makes OpenAI-compatible HTTP
# calls to a vLLM/Ollama server you run separately (see
# Docs/running_on_local_gpu.md) -- no GPU/CUDA is needed in this image.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Dependency layer: cached unless pyproject.toml/uv.lock/README.md change.
# README.md must be present here too: hatchling (the build backend) reads
# `readme = "README.md"` from pyproject.toml and fails the build if it's
# missing, even for the --no-install-project pass.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project

# Source + committed data layer (Dataset/prompts baked in for offline,
# byte-identical runs; results/ is bind-mounted at run time instead, see
# docker-compose.yml).
COPY src/ src/
COPY scripts/ scripts/
COPY tests/ tests/
COPY Dataset/ Dataset/
COPY prompts/ prompts/
RUN uv sync --frozen

ENV PATH="/app/.venv/bin:$PATH"

# No fixed entrypoint: every real invocation supplies explicit args, e.g.
#   docker compose run --rm fdpo python -m scripts.run_experiment --dataset aime ...
CMD ["python", "-c", "print('fdpo image ready. Invoke with: docker compose run --rm fdpo python -m scripts.run_experiment ...')"]

"""HuggingFace-transformers client — STUB for the TAMU team.

The preferred path for open models (Llama-3-8B, Qwen3-8B, DeepSeek) is to
serve them with vLLM and use OpenAICompatClient unchanged:

    pip install vllm
    python -m vllm.entrypoints.openai.api_server \
        --model meta-llama/Meta-Llama-3-8B-Instruct --port 8000

    # .env on the cluster:
    SOLVER_MODEL=meta-llama/Meta-Llama-3-8B-Instruct
    SOLVER_BASE_URL=http://localhost:8000/v1
    SOLVER_API_KEY=dummy

No code changes are needed for that route. Fill in this stub ONLY if direct
in-process transformers loading is required (e.g., no server allowed on the
cluster). To complete it:

1. Add torch + transformers to pyproject ([dependency-groups] hf = [...]).
2. In __init__: load AutoTokenizer + AutoModelForCausalLM (device_map="auto").
3. In _complete: apply tokenizer.apply_chat_template(messages), generate with
   temperature/max_new_tokens, decode only the new tokens, and return a
   ChatResult with real token counts (input_ids length / generated length).
4. json_mode has no server-side enforcement here — prompt-level "return only
   JSON" plus the judge's built-in parse-retry already handles this.
"""

from __future__ import annotations

from fdpo.clients.base import ChatResult, ModelClient


class HFTransformersClient(ModelClient):
    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "HFTransformersClient is a stub. Prefer serving the model with vLLM "
            "and using the OpenAI-compatible client (see this module's docstring "
            "for the exact commands). Implement this class only if in-process "
            "transformers loading is required."
        )

    def _complete(self, messages: list[dict], *, json_mode: bool,
                  temperature: float, max_tokens: int) -> ChatResult:
        raise NotImplementedError

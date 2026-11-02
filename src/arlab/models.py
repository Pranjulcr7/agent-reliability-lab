"""Model factories. The same harness and tools run with any smolagents Model.

- "reference": the scripted reference policy (not an LLM; zero cost).
- "transformers:<model_id>@<revision>": local inference via smolagents TransformersModel.
- "openai:<base_url>|<model>": any OpenAI-compatible server (e.g. a local vLLM / SGLang / llama.cpp server).

Real-model factories share one loaded model across episodes and enforce a global
request cap so an evaluation cannot run unbounded.
"""

from __future__ import annotations

import os
from typing import Any

from .harness import HarnessStop
from .policy import ReferencePolicy


class _Capped:
    """Delegates to a shared Model, stopping the episode once the global request cap is spent."""

    def __init__(self, inner, counter: dict[str, int], cap: int):
        self.inner, self.counter, self.cap = inner, counter, cap
        self.model_id = getattr(inner, "model_id", "unknown")

    def generate(self, *args, **kwargs):
        if self.counter["n"] >= self.cap:
            raise HarnessStop("global_request_cap", f"{self.cap} model requests for this run")
        self.counter["n"] += 1
        return self.inner.generate(*args, **kwargs)


def make_factory(spec: str, max_total_requests: int = 2000, temperature: float = 0.0, max_new_tokens: int = 384):
    if spec == "reference":
        return lambda view, seed: ReferencePolicy(view, seed)

    counter = {"n": 0}
    inner: Any
    if spec.startswith("transformers:"):
        from smolagents import TransformersModel

        model_id, _, revision = spec.split(":", 1)[1].partition("@")
        inner = TransformersModel(
            model_id=model_id,
            model_kwargs={"revision": revision or "main"},
            max_new_tokens=max_new_tokens,
            do_sample=temperature > 0,
            **({"temperature": temperature} if temperature > 0 else {}),
            apply_chat_template_kwargs={"enable_thinking": False},  # Qwen3: no thinking traces
        )
    elif spec.startswith("openai:"):
        from smolagents import OpenAIModel

        base_url, _, model = spec.split(":", 1)[1].partition("|")
        inner = OpenAIModel(model_id=model, api_base=base_url, api_key=os.environ.get("OPENAI_API_KEY", "EMPTY"),
                            temperature=temperature, max_tokens=max_new_tokens)
    else:
        raise ValueError(f"unknown model spec {spec!r}")

    def factory(view, seed):
        if spec.startswith("transformers:"):
            from transformers import set_seed

            set_seed(seed)
        return _Capped(inner, counter, max_total_requests)

    factory.counter = counter
    return factory

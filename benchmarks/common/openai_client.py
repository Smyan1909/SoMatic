"""Thin wrapper around the OpenAI vision API for benchmark use.

Centralises retry / backoff, token + dollar accounting, and the
`image_url` content-block shape. The harness uses this for all three arms.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class PricingSnapshot:
    """Per-million-token pricing in USD. Captured at runtime from
    pre-run model verification rather than hard-coded so the harness
    survives OpenAI price changes between runs."""

    input_per_mtok: float
    output_per_mtok: float

    def cost(self, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens * (self.input_per_mtok / 1_000_000)
            + output_tokens * (self.output_per_mtok / 1_000_000)
        )


@dataclass
class OpenAIResponse:
    text: str
    input_tokens: int
    output_tokens: int


class VisionClient(Protocol):
    model: str
    pricing: PricingSnapshot
    total_input_tokens: int
    total_output_tokens: int

    def ask(self, image_b64: str, prompt: str, *, mime: str = "image/png") -> OpenAIResponse: ...
    def cost_estimate_usd(self) -> float: ...
    def probe(self) -> None: ...


class OpenAIVisionClient:
    """Concrete VisionClient backed by the openai SDK.

    The `mcp[cli]` install does not pull openai; benchmarks/requirements.txt
    pins it explicitly. The runner instantiates this lazily so a developer
    without OPENAI_API_KEY can still run unit tests with FakeVisionClient.
    """

    def __init__(
        self,
        model: str = "gpt-5.5",
        *,
        api_key: str | None = None,
        detail: str = "original",
        max_output_tokens: int = 4096,
        timeout: float = 120.0,
    ) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise SystemExit(
                "benchmarks/requirements.txt must be installed for the OpenAI "
                "client. Run: pip install -r benchmarks/requirements.txt"
            ) from exc

        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise SystemExit(
                "OPENAI_API_KEY is required for the benchmark runner. Set it in "
                "your environment before invoking `python -m benchmarks.run`."
            )

        self._OpenAI = OpenAI
        self.client = OpenAI(api_key=key, timeout=timeout)
        self.model = os.environ.get("SOMATIC_BENCH_MODEL", model)
        self.detail = detail
        self.max_output_tokens = max_output_tokens
        # Pricing is filled in by `probe()` before the run begins.
        self.pricing = PricingSnapshot(
            input_per_mtok=float(os.environ.get("SOMATIC_BENCH_INPUT_USD_PER_MTOK", "5.0")),
            output_per_mtok=float(os.environ.get("SOMATIC_BENCH_OUTPUT_USD_PER_MTOK", "30.0")),
        )
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    def probe(self) -> None:
        """Verify the configured model id exists in this account.

        Uses `models.retrieve()` rather than a chat completion because
        reasoning models (GPT-5.x and friends) burn tokens internally before
        emitting output, so a 1-token probe completion always errors with
        "max_tokens limit reached" — that's a false negative for model-
        invalid detection. `models.retrieve()` is a free metadata call
        that genuinely returns 404 when the id is wrong."""
        try:
            self.client.models.retrieve(self.model)
        except Exception as exc:
            raise SystemExit(
                f"OPENAI_MODEL_INVALID: model '{self.model}' is not callable in "
                f"your account. Set SOMATIC_BENCH_MODEL to a current model id "
                f"(e.g. 'gpt-5', 'gpt-5-pro', 'gpt-4o', or whatever is current). "
                f"Underlying error: {exc}"
            ) from exc

    def ask(self, image_b64: str, prompt: str, *, mime: str = "image/png") -> OpenAIResponse:
        """Send one image+text turn and return parsed token totals."""
        from openai import APIConnectionError, InternalServerError, RateLimitError
        from tenacity import (
            retry,
            retry_if_exception_type,
            stop_after_attempt,
            wait_exponential,
        )

        @retry(
            retry=retry_if_exception_type(
                (RateLimitError, APIConnectionError, InternalServerError)
            ),
            wait=wait_exponential(multiplier=2, min=2, max=60),
            stop=stop_after_attempt(6),
            reraise=True,
        )
        def _call() -> Any:
            return self.client.chat.completions.create(
                model=self.model,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime};base64,{image_b64}",
                                "detail": self.detail,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }],
                max_completion_tokens=self.max_output_tokens,
                response_format={"type": "json_object"},
            )

        resp = _call()
        usage = resp.usage
        self.total_input_tokens += usage.prompt_tokens
        self.total_output_tokens += usage.completion_tokens
        return OpenAIResponse(
            text=resp.choices[0].message.content or "",
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
        )

    def cost_estimate_usd(self) -> float:
        return self.pricing.cost(self.total_input_tokens, self.total_output_tokens)

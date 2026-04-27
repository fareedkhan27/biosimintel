from __future__ import annotations

from typing import Any, NamedTuple

import httpx

from app.core.config import settings
from app.core.exceptions import AIClientException
from app.core.logging import get_logger

logger = get_logger(__name__)

PRIMARY_MODEL = settings.OPENROUTER_MODEL_PRIMARY
FALLBACK_MODEL = settings.OPENROUTER_MODEL_FALLBACK
MAX_TOKENS = 2000
TEMPERATURE = 0.1

# Approximate per-token pricing (USD) for cost estimation
_COST_PER_1K_INPUT: dict[str, float] = {
    "google/gemini-2.0-flash-001": 0.0001,
    "anthropic/claude-3.5-haiku": 0.0008,
}
_COST_PER_1K_OUTPUT: dict[str, float] = {
    "google/gemini-2.0-flash-001": 0.0004,
    "anthropic/claude-3.5-haiku": 0.004,
}


class AIResponse(NamedTuple):
    """Structured response from an AI generation call."""

    content: str
    model: str
    tokens_input: int
    tokens_output: int
    cost_usd: float


class AIClient:
    """Wrapper around OpenRouter with cost tracking and fallback."""

    def __init__(self) -> None:
        if not settings.OPENROUTER_ENABLED or not settings.OPENROUTER_API_KEY:
            raise RuntimeError(
                "OpenRouter not configured. Set OPENROUTER_API_KEY and OPENROUTER_ENABLED=true"
            )
        self.api_key = settings.OPENROUTER_API_KEY
        self.base_url = settings.OPENROUTER_BASE_URL
        self.client = httpx.AsyncClient(timeout=60.0)

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        max_tokens: int = MAX_TOKENS,
        temperature: float = TEMPERATURE,
    ) -> dict[str, Any]:
        model = model or PRIMARY_MODEL
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://biosim.platform",
            "X-Title": "Biosim",
        }
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        try:
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            logger.info(
                "AI call completed",
                model=model,
                usage=data.get("usage", {}),
            )
            return data
        except httpx.HTTPStatusError as exc:
            if model == PRIMARY_MODEL:
                logger.warning("Primary model failed, trying fallback", error=str(exc))
                return await self.chat_completion(
                    messages, model=FALLBACK_MODEL, max_tokens=max_tokens, temperature=temperature
                )
            raise AIClientException(f"AI request failed: {exc.response.text}") from exc
        except Exception as exc:
            raise AIClientException(f"AI request failed: {exc}") from exc

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = TEMPERATURE,
        max_tokens: int = MAX_TOKENS,
        response_format: dict[str, str] | None = None,
    ) -> AIResponse:
        """Convenience wrapper around chat_completion with structured output."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        payload_extra: dict[str, Any] = {}
        if response_format:
            payload_extra["response_format"] = response_format

        model = PRIMARY_MODEL
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://biosim.platform",
            "X-Title": "Biosim",
        }
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            **payload_extra,
        }

        try:
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            if model == PRIMARY_MODEL:
                logger.warning("Primary model failed, trying fallback", error=str(exc))
                model = FALLBACK_MODEL
                payload["model"] = model
                response = await self.client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
            else:
                raise AIClientException(f"AI request failed: {exc.response.text}") from exc
        except Exception as exc:
            raise AIClientException(f"AI request failed: {exc}") from exc

        usage = data.get("usage", {})
        tokens_input = usage.get("prompt_tokens", 0)
        tokens_output = usage.get("completion_tokens", 0)

        # Cost estimation
        in_cost = (tokens_input / 1000) * _COST_PER_1K_INPUT.get(model, 0.0001)
        out_cost = (tokens_output / 1000) * _COST_PER_1K_OUTPUT.get(model, 0.0004)
        cost_usd = round(in_cost + out_cost, 6)

        content = ""
        choices = data.get("choices", [])
        if choices:
            content = choices[0].get("message", {}).get("content", "")

        logger.info(
            "AI generate completed",
            model=model,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            cost_usd=cost_usd,
        )

        return AIResponse(
            content=content,
            model=model,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            cost_usd=cost_usd,
        )

    async def close(self) -> None:
        await self.client.aclose()

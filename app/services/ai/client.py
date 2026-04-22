from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings
from app.core.exceptions import AIClientException
from app.core.logging import get_logger

logger = get_logger(__name__)

PRIMARY_MODEL = settings.OPENROUTER_MODEL_PRIMARY
FALLBACK_MODEL = settings.OPENROUTER_MODEL_FALLBACK
MAX_TOKENS = 2000
TEMPERATURE = 0.1


class AIClient:
    """Wrapper around OpenRouter with cost tracking and fallback."""

    def __init__(self) -> None:
        self.api_key = settings.OPENROUTER_API_KEY
        self.base_url = "https://openrouter.ai/api/v1"
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

    async def close(self) -> None:
        await self.client.aclose()

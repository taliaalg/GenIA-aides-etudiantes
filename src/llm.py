"""Client LLM minimal, compatible avec toute API au format OpenAI."""
import time
from dataclasses import dataclass, field

from openai import OpenAI

from . import config


@dataclass
class LLMResponse:
    content: str
    tool_calls: list = field(default_factory=list)  # [{"id", "name", "arguments"(str)}]
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_s: float = 0.0
    raw_message: dict | None = None


class LLM:
    def __init__(self, model: str | None = None):
        self.client = OpenAI(base_url=config.LLM_BASE_URL, api_key=config.LLM_API_KEY)
        self.model = model or config.LLM_MODEL

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        kwargs = {"model": self.model, "messages": messages, "temperature": config.LLM_TEMPERATURE}
        if tools:
            kwargs["tools"] = tools
        t0 = time.perf_counter()
        resp = self.client.chat.completions.create(**kwargs)
        latency = time.perf_counter() - t0
        msg = resp.choices[0].message
        calls = [
            {"id": c.id, "name": c.function.name, "arguments": c.function.arguments or "{}"}
            for c in (msg.tool_calls or [])
        ]
        usage = resp.usage
        raw = {"role": "assistant", "content": msg.content or ""}
        if calls:
            raw["tool_calls"] = [
                {"id": c["id"], "type": "function",
                 "function": {"name": c["name"], "arguments": c["arguments"]}}
                for c in calls
            ]
        return LLMResponse(
            content=msg.content or "",
            tool_calls=calls,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            latency_s=latency,
            raw_message=raw,
        )

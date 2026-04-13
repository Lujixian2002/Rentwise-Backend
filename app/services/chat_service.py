from __future__ import annotations

import json

from openai import AsyncOpenAI, APITimeoutError

from app.core.config import Settings
from app.schemas.chat import ChatMessage, ChatResponse, PreferenceWeights

_SYSTEM_PROMPT = """You are a neighborhood recommendation assistant for the Irvine, CA area.
Your job is to have a friendly, concise conversation to understand what the user values when \
choosing where to live, then translate that into preference weights across 5 dimensions.

The 5 dimensions are:
- safety: Low crime, feeling safe at night, well-lit streets
- transit: Public transit access, short commutes, low car dependence
- convenience: Walkability to groceries, restaurants, daily errands
- parking: Easy and affordable parking and car storage
- environment: Quiet streets, green space, low noise pollution

RULES:
1. Keep replies to 2-3 sentences max.
2. Ask a brief follow-up only if the user's message is completely vague (e.g. just "hello").
3. After EVERY message you MUST respond with a valid JSON object — no markdown, no extra text — \
in exactly this format:
{"reply": "...", "weights": {"safety": N, "transit": N, "convenience": N, "parking": N, \
"environment": N}, "ready_to_recommend": true/false}
4. All 5 weights must be numbers between 0 and 100 and sum to exactly 100. \
Start equal (20 each) and adjust as the user reveals preferences.
5. Set ready_to_recommend to true as soon as the user has expressed any clear preference \
(i.e. at least one weight has meaningfully changed from 20). Be generous — one clear preference is enough.
6. Do NOT name or recommend specific neighborhoods — the ranking system handles that.
7. Output ONLY the JSON object, nothing else."""

_MAX_HISTORY = 20
_DEFAULT_WEIGHTS = PreferenceWeights(
    safety=20, transit=20, convenience=20, parking=20, environment=20
)


async def get_chat_response(
    messages: list[ChatMessage], settings: Settings
) -> ChatResponse:
    client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=30.0)

    # Cap history to avoid runaway token usage
    trimmed = messages[-_MAX_HISTORY:]

    openai_messages = [{"role": "system", "content": _SYSTEM_PROMPT}] + [
        {"role": m.role, "content": m.content} for m in trimmed
    ]

    try:
        completion = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=openai_messages,
            response_format={"type": "json_object"},
            temperature=0.7,
            max_tokens=300,
        )
        raw = completion.choices[0].message.content or ""
        data = json.loads(raw)

        weights_data = data.get("weights", {})
        weights = PreferenceWeights(
            safety=weights_data.get("safety"),
            transit=weights_data.get("transit"),
            convenience=weights_data.get("convenience"),
            parking=weights_data.get("parking"),
            environment=weights_data.get("environment"),
        )

        return ChatResponse(
            reply=str(data.get("reply", "")),
            weights=weights,
            ready_to_recommend=bool(data.get("ready_to_recommend", False)),
        )

    except APITimeoutError:
        return ChatResponse(
            reply="The AI took too long to respond. Please try again.",
            weights=_DEFAULT_WEIGHTS,
            ready_to_recommend=False,
        )
    except (json.JSONDecodeError, KeyError, IndexError):
        # Return the raw text as a reply with default weights if parsing fails
        reply_text = raw if raw else "Sorry, I had trouble processing that. Could you try again?"
        return ChatResponse(
            reply=reply_text,
            weights=_DEFAULT_WEIGHTS,
            ready_to_recommend=False,
        )

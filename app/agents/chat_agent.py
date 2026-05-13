from __future__ import annotations

import json

from openai import AsyncOpenAI

from app.schemas.agent import (
    AgentChatResponse,
    AgentSkillCall,
    AgentTraceStep,
)
from app.schemas.chat import ChatMessage, PreferenceWeights

_ROUTER_SYSTEM_PROMPT = """You route RentWise chat messages to agent skills.
Return only a valid JSON object:
{
  "intent": "community_search|community_report|web_research|preference_extraction|general_chat",
  "community_name": "... or null",
  "community_id": "... or null",
  "city": "... or null",
  "state": "... or null",
  "web_query": "... or null"
}

Rules:
1. community_search: user asks about, searches, or wants data for a community/neighborhood.
2. community_report: user asks for a page/report/details for a specific community.
3. web_research: user explicitly asks to search the web or external sources.
4. preference_extraction: user describes living preferences or priorities.
5. general_chat: greetings, vague messages, or unsupported requests.
6. If a place is named but city/state are absent, leave city/state null."""

_FINAL_SYSTEM_PROMPT = """You are a concise RentWise assistant.
Summarize the agent result for a renter in 2-4 sentences.
Do not invent facts. Mention sources or missing data when relevant."""


async def run_agent_chat(agent, messages: list[ChatMessage]) -> AgentChatResponse:
    trace = [
        AgentTraceStep(
            step="chat_intent_routing",
            status="success" if agent.settings.openai_api_key else "skipped",
            message=(
                "LLM routed the chat message to an agent intent."
                if agent.settings.openai_api_key
                else "LLM routing skipped because OpenAI API key is not configured."
            ),
        )
    ]
    route = await _route_intent(agent.settings, messages)
    intent = route["intent"]
    skill_calls: list[AgentSkillCall] = []
    community_search = None
    community_report = None
    weights = None
    ready_to_recommend = False

    if intent == "community_search":
        community_name = route.get("community_name") or _latest_user_message(messages)
        community_search = await agent.search_community(
            community_name=community_name,
            city=route.get("city"),
            state=route.get("state"),
        )
        skill_calls.append(
            AgentSkillCall(
                name="community_search",
                status="success",
                detail=community_search.status,
            )
        )
        trace.extend(community_search.agent_trace)
        reply = await _final_reply(
            agent.settings,
            messages,
            {
                "intent": intent,
                "community_search": community_search.model_dump(),
            },
        )
        return AgentChatResponse(
            intent=intent,
            reply=reply,
            community_search=community_search,
            skill_calls=skill_calls,
            agent_trace=trace,
        )

    if intent == "community_report":
        community_id = route.get("community_id")
        if not community_id:
            community_name = route.get("community_name") or _latest_user_message(messages)
            community_search = await agent.search_community(
                community_name=community_name,
                city=route.get("city"),
                state=route.get("state"),
            )
            community_id = community_search.matched_community_id
            skill_calls.append(
                AgentSkillCall(
                    name="community_search",
                    status="success",
                    detail=community_search.status,
                )
            )
            trace.extend(community_search.agent_trace)

        if community_id:
            community_report = await agent.generate_community_report(community_id)
            skill_calls.append(
                AgentSkillCall(
                    name="community_report",
                    status="success",
                    detail=community_id,
                )
            )
            trace.extend(community_report.agent_trace)

        reply = await _final_reply(
            agent.settings,
            messages,
            {
                "intent": intent,
                "community_search": (
                    community_search.model_dump() if community_search else None
                ),
                "community_report": (
                    community_report.model_dump() if community_report else None
                ),
            },
        )
        return AgentChatResponse(
            intent=intent,
            reply=reply,
            community_search=community_search,
            community_report=community_report,
            skill_calls=skill_calls,
            agent_trace=trace,
        )

    if intent == "web_research":
        query = route.get("web_query") or route.get("community_name") or _latest_user_message(messages)
        skill = agent.skill_registry.get("web_research")
        research = await skill.run({"query": query}, agent.context)
        skill_calls.append(
            AgentSkillCall(
                name="web_research",
                status="success" if research.sources else "failed",
                detail=query,
            )
        )
        trace.append(
            AgentTraceStep(
                step="web_research",
                status="success" if research.sources else "failed",
                message=(
                    "Searched external web sources."
                    if research.sources
                    else "Web research was unavailable or returned no sources."
                ),
                detail={"query": query, "source_count": len(research.sources)},
            )
        )
        return AgentChatResponse(
            intent=intent,
            reply=research.summary,
            sources=research.sources,
            skill_calls=skill_calls,
            agent_trace=trace,
        )

    if intent == "preference_extraction":
        skill = agent.skill_registry.get("preference_extraction")
        chat = await skill.run(
            {"messages": [message.model_dump() for message in messages]},
            agent.context,
        )
        weights = chat.weights
        ready_to_recommend = chat.ready_to_recommend
        skill_calls.append(
            AgentSkillCall(
                name="preference_extraction",
                status="success",
            )
        )
        return AgentChatResponse(
            intent=intent,
            reply=chat.reply,
            weights=weights,
            ready_to_recommend=ready_to_recommend,
            skill_calls=skill_calls,
            agent_trace=trace,
        )

    reply = await _general_reply(agent.settings, messages)
    return AgentChatResponse(
        intent="general_chat",
        reply=reply,
        weights=PreferenceWeights(
            safety=20,
            transit=20,
            convenience=20,
            parking=20,
            environment=20,
        ),
        skill_calls=skill_calls,
        agent_trace=trace,
    )


async def _route_intent(settings, messages: list[ChatMessage]) -> dict:
    if not settings.openai_api_key:
        return _fallback_route(messages)

    client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=20.0)
    try:
        completion = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _ROUTER_SYSTEM_PROMPT},
                *[
                    {"role": message.role, "content": message.content}
                    for message in messages[-8:]
                ],
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=300,
        )
        data = json.loads(completion.choices[0].message.content or "{}")
    except Exception:
        return _fallback_route(messages)

    intent = str(data.get("intent") or "").strip()
    if intent not in {
        "community_search",
        "community_report",
        "web_research",
        "preference_extraction",
        "general_chat",
    }:
        intent = "general_chat"
    return {
        "intent": intent,
        "community_name": _optional_text(data.get("community_name")),
        "community_id": _optional_text(data.get("community_id")),
        "city": _optional_text(data.get("city")),
        "state": _optional_text(data.get("state")),
        "web_query": _optional_text(data.get("web_query")),
    }


def _fallback_route(messages: list[ChatMessage]) -> dict:
    text = _latest_user_message(messages).lower()
    if any(token in text for token in ["web", "search", "source", "online"]):
        return {"intent": "web_research", "web_query": _latest_user_message(messages)}
    if any(token in text for token in ["report", "page", "details"]):
        return {"intent": "community_report", "community_name": _latest_user_message(messages)}
    if any(token in text for token in ["community", "neighborhood", "area", "about"]):
        return {"intent": "community_search", "community_name": _latest_user_message(messages)}
    if any(token in text for token in ["safe", "parking", "commute", "quiet", "transit"]):
        return {"intent": "preference_extraction"}
    return {"intent": "general_chat"}


async def _final_reply(settings, messages: list[ChatMessage], result: dict) -> str:
    if not settings.openai_api_key:
        return _fallback_final_reply(result)
    client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=20.0)
    try:
        completion = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _FINAL_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "latest_user_message": _latest_user_message(messages),
                            "agent_result": result,
                        },
                        ensure_ascii=True,
                    ),
                },
            ],
            temperature=0.35,
            max_tokens=350,
        )
        return completion.choices[0].message.content or _fallback_final_reply(result)
    except Exception:
        return _fallback_final_reply(result)


async def _general_reply(settings, messages: list[ChatMessage]) -> str:
    if not settings.openai_api_key:
        return "I can help search communities, generate community reports, research web sources, or learn your rental preferences."
    client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=20.0)
    try:
        completion = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a concise RentWise rental assistant. Briefly explain what you can do.",
                },
                *[
                    {"role": message.role, "content": message.content}
                    for message in messages[-6:]
                ],
            ],
            temperature=0.4,
            max_tokens=180,
        )
        return completion.choices[0].message.content or "How can I help with your rental search?"
    except Exception:
        return "I can help search communities, generate reports, research web sources, or learn your rental preferences."


def _fallback_final_reply(result: dict) -> str:
    if result.get("community_report"):
        report = result["community_report"]
        return f"Generated a report for {report.get('title') or report.get('community_id')}."
    if result.get("community_search"):
        search = result["community_search"]
        return f"Community search finished with status {search.get('status')}."
    return "Done."


def _latest_user_message(messages: list[ChatMessage]) -> str:
    for message in reversed(messages):
        if message.role == "user":
            return message.content
    return ""


def _optional_text(value) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    if not text or text.lower() == "null":
        return None
    return text


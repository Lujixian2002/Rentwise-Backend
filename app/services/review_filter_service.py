import json
import re
from datetime import datetime
from dataclasses import dataclass
from hashlib import sha256
from typing import Iterable

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import ReviewPost


_REVIEW_FILTER_SYSTEM_PROMPT = """You classify public comments for a rental, neighborhood, housing, and moving-cost UI.

Return only structured JSON matching the requested schema.

Be conservative: the cost of incorrectly dropping a useful comment is higher than the cost of keeping a mildly noisy one.

Keep a comment if it contains, or may reasonably contain, useful signal about:
- a place, apartment, neighborhood, rent, lease, safety, noise, commute, parking, maintenance, amenities, management, or resident experience
- moving, move-out, relocation, PODS/storage containers, mileage charges, quotes, invoices, deposits, monthly costs, payment timing, or housing-related services
- concrete prices or cost reactions, even when context is short, for example "$12,000 a month in Washington state.", "the 7ft pod was quoted at $3900", "43k a month?", or "The charge for that mileage was very expensive."
- concrete questions that reveal user needs about moving/housing logistics, for example "3 separate invoices as installments monthly?"
- comments saying the video answered questions when the video/topic appears to be about moving, housing, rent, storage, or relocation

Important preservation rule:
- Keep very short comments when they express a concrete opinion, disagreement, warning, complaint, praise, surprise, or emotional reaction that could be about the place.
- For example, keep: "Most nicest?!?!?!? No!! No!!! Noooooooooo. Lol"

Drop only comments that are clearly useless for this UI:
- advertising, promotions, scams, link spam, giveaways, referral codes
- pure creator/video/channel engagement with no housing, moving, place, price, or logistics signal
- generic off-topic praise such as "I love vlogs like these!" or "You made my day"
- unrelated comments about sharks, celebrity/news/crime reactions, political insults, medical/end-of-life advice, or random personal stories that do not mention housing, moving, costs, or place experience
- empty, unreadable, duplicate-like filler, bot noise, or emoji-only reactions

When uncertain, keep the comment."""

_REVIEW_FILTER_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "post_id": {"type": "string"},
                    "keep": {"type": "boolean"},
                    "category": {
                        "type": "string",
                        "enum": [
                            "useful",
                            "short_opinion",
                            "moving_cost",
                            "housing_cost",
                            "logistics_question",
                            "advertising",
                            "off_topic",
                            "creator_engagement",
                            "noise",
                        ],
                    },
                    "reason": {"type": "string"},
                },
                "required": ["post_id", "keep", "category", "reason"],
            },
        }
    },
    "required": ["decisions"],
}

_AI_REVIEW_BATCH_SIZE = 50
_PROMPT_VERSION = "2026-04-29-v2"


@dataclass(frozen=True)
class ReviewFilterDecision:
    post_id: str
    keep: bool
    category: str
    reason: str


async def filter_reviews_for_community_ui(
    reviews: Iterable[ReviewPost],
    settings: Settings,
    db: Session,
    refresh: bool = False,
) -> list[ReviewPost]:
    review_list = list(reviews)
    if not review_list:
        return review_list

    if not settings.openai_api_key:
        return _rule_based_filter(review_list)

    model = settings.openai_review_filter_model
    cached_by_hash = _load_cached_decisions_by_hash(db, review_list, model)
    candidates: list[ReviewPost] = []
    pending_by_hash: dict[str, list[ReviewPost]] = {}
    for review in review_list:
        review_hash = _hash_review_text(review.body_text)
        if not review_hash:
            continue
        if not refresh and _has_valid_cached_decision(review, review_hash, model):
            continue
        if not refresh and review_hash in cached_by_hash:
            _apply_cached_decision(review, cached_by_hash[review_hash], review_hash, model)
            continue
        if _should_send_to_ai(review):
            pending = pending_by_hash.setdefault(review_hash, [])
            pending.append(review)
            if len(pending) == 1:
                candidates.append(review)

    if not candidates:
        db.commit()
        return _filter_by_cached_decisions(review_list)

    try:
        decisions = await _classify_reviews(candidates, settings)
    except Exception:
        return _rule_based_filter(review_list)

    decisions_by_id = {decision.post_id: decision for decision in decisions}
    for review_hash, matching_reviews in pending_by_hash.items():
        review = matching_reviews[0]
        review_hash = _hash_review_text(review.body_text)
        if not review_hash:
            continue
        decision = decisions_by_id.get(review.post_id)
        if decision is None:
            keep = not _looks_like_low_value(review.body_text)
            decision = ReviewFilterDecision(
                post_id=review.post_id,
                keep=keep,
                category="useful" if keep else "noise",
                reason="fallback_rule",
            )
        for matching_review in matching_reviews:
            matching_decision = ReviewFilterDecision(
                post_id=matching_review.post_id,
                keep=decision.keep,
                category=decision.category,
                reason=decision.reason,
            )
            _save_decision(matching_review, matching_decision, review_hash, model)

    db.commit()
    return _filter_by_cached_decisions(review_list)


async def _classify_reviews(
    reviews: list[ReviewPost],
    settings: Settings,
) -> list[ReviewFilterDecision]:
    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        timeout=settings.openai_review_filter_timeout_sec,
    )
    decisions: list[ReviewFilterDecision] = []
    for start in range(0, len(reviews), _AI_REVIEW_BATCH_SIZE):
        decisions.extend(
            await _classify_review_batch(
                client,
                settings,
                reviews[start : start + _AI_REVIEW_BATCH_SIZE],
            )
        )
    return decisions


async def _classify_review_batch(
    client: AsyncOpenAI,
    settings: Settings,
    reviews: list[ReviewPost],
) -> list[ReviewFilterDecision]:
    payload = {
        "comments": [
            {
                "post_id": review.post_id,
                "platform": review.platform,
                "body_text": _normalize_text(review.body_text),
                "like_count": review.like_count,
                "parent_id": review.parent_id,
            }
            for review in reviews
        ]
    }

    raw = await _create_structured_response(client, settings, payload)
    data = json.loads(raw)
    return _parse_decisions(data)


async def _create_structured_response(
    client: AsyncOpenAI,
    settings: Settings,
    payload: dict,
) -> str:
    user_prompt = json.dumps(payload, ensure_ascii=True)

    if hasattr(client, "responses"):
        response = await client.responses.create(
            model=settings.openai_review_filter_model,
            input=[
                {"role": "system", "content": _REVIEW_FILTER_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "review_filter_decisions",
                    "strict": True,
                    "schema": _REVIEW_FILTER_SCHEMA,
                }
            },
            max_output_tokens=2500,
        )
        return _extract_response_text(response)

    completion = await client.chat.completions.create(
        model=settings.openai_review_filter_model,
        messages=[
            {"role": "system", "content": _REVIEW_FILTER_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        max_tokens=2500,
    )
    return completion.choices[0].message.content or "{}"


def _parse_decisions(data: dict) -> list[ReviewFilterDecision]:
    decisions: list[ReviewFilterDecision] = []
    for item in data.get("decisions", []):
        post_id = item.get("post_id")
        if not isinstance(post_id, str) or not post_id:
            continue
        decisions.append(
            ReviewFilterDecision(
                post_id=post_id,
                keep=bool(item.get("keep", True)),
                category=str(item.get("category") or "useful"),
                reason=str(item.get("reason") or ""),
            )
        )
    return decisions


def _load_cached_decisions_by_hash(
    db: Session,
    reviews: list[ReviewPost],
    model: str,
) -> dict[str, ReviewFilterDecision]:
    hashes = {
        review_hash
        for review in reviews
        if (review_hash := _hash_review_text(review.body_text))
    }
    if not hashes:
        return {}

    stmt = (
        select(
            ReviewPost.ai_filter_text_hash,
            ReviewPost.ai_filter_keep,
            ReviewPost.ai_filter_category,
            ReviewPost.ai_filter_reason,
        )
        .where(ReviewPost.ai_filter_text_hash.in_(hashes))
        .where(ReviewPost.ai_filter_model == model)
        .where(ReviewPost.ai_filter_prompt_version == _PROMPT_VERSION)
        .where(ReviewPost.ai_filter_keep.is_not(None))
    )

    cached: dict[str, ReviewFilterDecision] = {}
    for review_hash, keep, category, reason in db.execute(stmt).all():
        if review_hash and review_hash not in cached:
            cached[review_hash] = ReviewFilterDecision(
                post_id="",
                keep=bool(keep),
                category=category or "useful",
                reason=reason or "cached_by_text_hash",
            )
    return cached


def _has_valid_cached_decision(review: ReviewPost, review_hash: str, model: str) -> bool:
    return (
        review.ai_filter_keep is not None
        and review.ai_filter_text_hash == review_hash
        and review.ai_filter_model == model
        and review.ai_filter_prompt_version == _PROMPT_VERSION
    )


def _apply_cached_decision(
    review: ReviewPost,
    decision: ReviewFilterDecision,
    review_hash: str,
    model: str,
) -> None:
    copied = ReviewFilterDecision(
        post_id=review.post_id,
        keep=decision.keep,
        category=decision.category,
        reason=decision.reason,
    )
    _save_decision(review, copied, review_hash, model)


def _save_decision(
    review: ReviewPost,
    decision: ReviewFilterDecision,
    review_hash: str,
    model: str,
) -> None:
    review.ai_filter_keep = decision.keep
    review.ai_filter_category = decision.category
    review.ai_filter_reason = decision.reason[:1000]
    review.ai_filter_model = model
    review.ai_filter_prompt_version = _PROMPT_VERSION
    review.ai_filter_text_hash = review_hash
    review.ai_filter_checked_at = datetime.utcnow()


def _filter_by_cached_decisions(reviews: list[ReviewPost]) -> list[ReviewPost]:
    filtered: list[ReviewPost] = []
    for review in reviews:
        if review.ai_filter_keep is None:
            if not _looks_like_low_value(review.body_text):
                filtered.append(review)
        elif review.ai_filter_keep:
            filtered.append(review)
    return filtered


def _rule_based_filter(reviews: list[ReviewPost]) -> list[ReviewPost]:
    return [review for review in reviews if not _looks_like_low_value(review.body_text)]


def _should_send_to_ai(review: ReviewPost) -> bool:
    text = _normalize_text(review.body_text)
    return bool(text)


def _looks_like_low_value(text: str | None) -> bool:
    normalized = _normalize_text(text).lower()
    if not normalized:
        return True

    spam_signals = (
        "http://",
        "https://",
        "promo code",
        "referral",
        "subscribe",
        "check out my channel",
        "dm me",
        "whatsapp",
        "telegram",
    )
    if any(signal in normalized for signal in spam_signals):
        return True

    creator_only_patterns = (
        r"^i love (your )?(vlogs?|videos?|content)( like (this|these))?!?$",
        r"^(great|nice|cool|awesome|amazing) (vlog|video|content)!?$",
        r"^thanks for (sharing|the video)!?$",
    )
    return any(re.match(pattern, normalized) for pattern in creator_only_patterns)


def _normalize_text(text: str | None, limit: int = 500) -> str:
    normalized = " ".join((text or "").split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def _hash_review_text(text: str | None) -> str | None:
    normalized = _normalize_text(text, limit=5000).lower()
    if not normalized:
        return None
    return sha256(normalized.encode("utf-8")).hexdigest()


def _extract_response_text(response) -> str:
    output_text = _obj_get(response, "output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    chunks: list[str] = []
    for output_item in _obj_get(response, "output", []) or []:
        if _obj_get(output_item, "type") != "message":
            continue
        for content_item in _obj_get(output_item, "content", []) or []:
            text = _obj_get(content_item, "text")
            if isinstance(text, str) and text.strip():
                chunks.append(text.strip())
    return "\n".join(chunks).strip()


def _obj_get(obj, key: str, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)

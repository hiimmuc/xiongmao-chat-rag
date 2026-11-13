"""Usage ledger and cost estimates.

Every paid provider call follows the same life cycle:
    intent()   - row written before the call, so a crash leaves it visible as unknown
    dispatch() - the request was sent
    finalize() - provider-reported tokens and the estimated cost
Unknown tokens or cost stay None; they are never counted as zero.
"""

import json
from datetime import datetime, timedelta
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select

from app.core import database
from app.core.config import settings
from app.models import Usage, User

# ---- ledger ---------------------------------------------------------------------------------


def estimate_cost(input_tokens, output_tokens, cached_tokens, rate):
    """Estimated USD for one call from per-million-token rates, or None when any needed count or rate is missing."""
    if input_tokens is None or output_tokens is None or not rate:
        return None
    if "input" not in rate or "output" not in rate:
        return None
    cached = min(cached_tokens or 0, input_tokens)
    if cached and "cached_input" not in rate:
        return None
    return (
        Decimal(input_tokens - cached) * Decimal(rate["input"])
        + Decimal(cached) * Decimal(rate.get("cached_input", "0"))
        + Decimal(output_tokens) * Decimal(rate["output"])
    ) / Decimal(1000000)


@lru_cache
def _rates():
    return json.loads(Path(__file__).with_name("rates.json").read_text())


def rate_for(model_id):
    return settings().catalog().get(model_id, {}).get("rate", _rates().get(model_id, {}))


def intent(user_id, model_id, provider, operation, **refs):
    """Record a usage row before a paid call. Returns the row ID."""
    with database.Session() as db:
        u = db.get(User, user_id)
        if not u or u.state != "active":
            raise ValueError("Account unavailable")
        row = Usage(
            user_id=user_id,
            model_id=model_id,
            provider=provider,
            operation=operation,
            rate=rate_for(model_id),
            **refs,
        )
        db.add(row)
        db.commit()
        return row.id


def dispatch(id):
    """Mark the intent as sent to the provider."""
    with database.Session() as db:
        row = db.get(Usage, id)
        if row:
            row.status = "dispatched"
            db.commit()


def finalize(id, metadata=None, status="succeeded"):
    """Store the provider-reported usage and final status on the intent exactly once."""
    with database.Session() as db:
        row = db.get(Usage, id)
        if not row:
            return
        user = db.get(User, row.user_id)
        if not user or user.state != "active":
            return
        row.status = status
        if metadata:
            row.input_tokens = metadata.get("input_tokens")
            row.output_tokens = metadata.get("output_tokens")
            row.cached_tokens = metadata.get("cached_tokens", 0)
            row.provider_request_id = metadata.get("request_id")
            row.cost_usd = estimate_cost(row.input_tokens, row.output_tokens, row.cached_tokens, row.rate)
        db.commit()


# ---- reading ----------------------------------------------------------------------------------


def brief(x):
    """Tokens and cost of one call, as shown under an answer."""
    known = x.input_tokens is not None and x.output_tokens is not None
    return dict(
        input_tokens=x.input_tokens,
        output_tokens=x.output_tokens,
        total_tokens=x.input_tokens + x.output_tokens if known else None,
        cost_usd=str(x.cost_usd) if x.cost_usd is not None else None,
    )


def usage_briefs(db, generation_ids):
    """Chat-call tokens and cost per generation (latest call wins)."""
    rows = db.scalars(
        select(Usage)
        .where(Usage.generation_id.in_(generation_ids), Usage.operation == "chat")
        .order_by(Usage.created_at)
    )
    return {x.generation_id: brief(x) for x in rows}


def usage_rows(db, user_id, start, end, tz, **filters):
    """The user's calls from `start` to `end` (dates, inclusive, in `tz`), newest first.

    `filters` are column=value pairs (provider, model_id, conversation_id, operation); None is ignored."""
    since = datetime.combine(start, datetime.min.time(), tzinfo=tz)
    until = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=tz)
    q = select(Usage).where(Usage.user_id == user_id, Usage.created_at >= since, Usage.created_at < until)
    for column, value in filters.items():
        if value:
            q = q.where(getattr(Usage, column) == value)
    return db.scalars(q.order_by(Usage.created_at.desc(), Usage.id.desc())).all()


def summary(rows):
    """Totals for a group of calls; `complete` is False when any tokens or prices are unknown."""
    unknown = sum(x.input_tokens is None or x.output_tokens is None for x in rows)
    unpriced = sum(x.cost_usd is None for x in rows)
    cost = sum((x.cost_usd for x in rows if x.cost_usd is not None), Decimal(0))
    return dict(
        confirmed_requests=sum(x.status not in ("pending_dispatch", "unknown") for x in rows),
        unknown_dispatches=sum(x.status in ("pending_dispatch", "unknown") for x in rows),
        known_input_tokens=sum(x.input_tokens or 0 for x in rows),
        known_output_tokens=sum(x.output_tokens or 0 for x in rows),
        known_total_tokens=sum((x.input_tokens or 0) + (x.output_tokens or 0) for x in rows),
        known_cost_usd=str(cost),
        unknown_usage_records=unknown,
        unpriced_records=unpriced,
        complete=unknown == 0 and unpriced == 0,
    )

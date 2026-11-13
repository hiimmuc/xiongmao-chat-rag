"""/usage: requests, tokens and estimated cost, as a summary, per day, per model or per request."""

from collections import defaultdict
from datetime import datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.database import get_db
from app.core.security import current_user
from app.services.usage import summary, usage_rows

router = APIRouter(tags=["usage"])


def usage_json(x):
    known = x.input_tokens is not None and x.output_tokens is not None
    return dict(
        id=x.id,
        created_at=x.created_at,
        provider=x.provider,
        model_id=x.model_id,
        operation=x.operation,
        status=x.status,
        input_tokens=x.input_tokens,
        output_tokens=x.output_tokens,
        total_tokens=x.input_tokens + x.output_tokens if known else None,
        cost_usd=str(x.cost_usd) if x.cost_usd is not None else None,
        conversation_id=x.conversation_id,
        generation_id=x.generation_id,
        complete=known and x.cost_usd is not None,
    )


def filtered_usage(
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    timezone_name: str = Query("UTC", alias="timezone"),
    provider: str | None = None,
    model_id: str | None = None,
    conversation_id: UUID | None = None,
    operation: str | None = None,
    user=Depends(current_user),
    db=Depends(get_db),
):
    """Shared filters of every usage route (last 30 days by default). Returns (rows, period)."""
    try:
        tz = ZoneInfo(timezone_name)
        today = datetime.now(tz).date()
        start = datetime.fromisoformat(from_).date() if from_ else today - timedelta(days=29)
        end = datetime.fromisoformat(to).date() if to else today
        if not 0 <= (end - start).days < 366:
            raise ValueError()
    except (ValueError, ZoneInfoNotFoundError):
        raise HTTPException(422, "Invalid date range or timezone") from None
    rows = usage_rows(
        db,
        user.id,
        start,
        end,
        tz,
        provider=provider,
        model_id=model_id,
        conversation_id=str(conversation_id) if conversation_id else None,
        operation=operation,
    )
    return rows, {"from": start.isoformat(), "to": end.isoformat(), "timezone": timezone_name}


@router.get("/usage/summary")
def usage_summary(data=Depends(filtered_usage)):
    rows, period = data
    return dict(**period, **summary(rows))


@router.get("/usage/daily")
def usage_daily(data=Depends(filtered_usage)):
    rows, period = data
    tz = ZoneInfo(period["timezone"])
    groups = defaultdict(list)
    for row in rows:
        groups[row.created_at.astimezone(tz).date().isoformat()].append(row)
    day = datetime.fromisoformat(period["from"]).date()
    end = datetime.fromisoformat(period["to"]).date()
    items = []
    while day <= end:
        key = day.isoformat()
        items.append(dict(date=key, **summary(groups[key])))
        day += timedelta(days=1)
    return dict(**period, items=items)


@router.get("/usage/models")
def usage_models(data=Depends(filtered_usage)):
    rows, period = data
    groups = defaultdict(list)
    for row in rows:
        groups[(row.provider, row.model_id, row.operation)].append(row)
    return dict(
        **period,
        items=[
            dict(provider=k[0], model_id=k[1], operation=k[2], **summary(v))
            for k, v in sorted(groups.items())
        ],
    )


@router.get("/usage/requests")
def usage_requests(
    cursor: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100), data=Depends(filtered_usage)
):
    rows, period = data
    result = rows[cursor : cursor + limit]
    return dict(
        **period,
        items=[usage_json(x) for x in result],
        next_cursor=str(cursor + limit) if len(rows) > cursor + limit else None,
    )

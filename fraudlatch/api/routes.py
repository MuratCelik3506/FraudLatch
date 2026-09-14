"""Transaction and service health routes."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import desc, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from fraudlatch.api.repository import (
    create_outbox_event,
    create_transaction,
    get_transaction,
    matches_payload,
)
from fraudlatch.api.risk_repository import get_risk_assessment
from fraudlatch.api.schemas import (
    HighRiskResponse,
    RiskAssessmentResponse,
    TransactionAccepted,
    TransactionIn,
    TransactionResponse,
)
from fraudlatch.db.models import RiskAssessment

router = APIRouter()


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Provide a request-scoped async database session."""

    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        try:
            yield session
        except BaseException:
            await session.rollback()
            raise


@router.get("/health")
async def health() -> dict[str, str]:
    """Return process liveness without checking dependencies."""

    return {"status": "ok"}


@router.get("/ready")
async def ready(
    response: Response,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, str]:
    """Return readiness only when PostgreSQL is reachable."""

    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_ready"}
    return {"status": "ready"}


@router.post(
    "/v1/transactions",
    response_model=TransactionAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest_transaction(
    payload: TransactionIn,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> TransactionAccepted:
    """Accept a transaction with database-authoritative idempotency."""

    existing = await get_transaction(session, payload.transaction_id)
    if existing is not None:
        if matches_payload(existing, payload):
            return TransactionAccepted(
                transaction_id=payload.transaction_id, status="already_accepted"
            )
        raise HTTPException(  # noqa: B904
            status_code=status.HTTP_409_CONFLICT, detail="transaction ID conflict"
        ) from None

    try:
        await create_transaction(session, payload)
        await create_outbox_event(session, payload)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = await get_transaction(session, payload.transaction_id)
        if existing is not None and matches_payload(existing, payload):
            return TransactionAccepted(
                transaction_id=payload.transaction_id, status="already_accepted"
            )
        raise HTTPException(  # noqa: B904
            status_code=status.HTTP_409_CONFLICT, detail="transaction ID conflict"
        ) from None
    return TransactionAccepted(transaction_id=payload.transaction_id, status="accepted")


@router.get("/v1/transactions/{transaction_id}", response_model=TransactionResponse)
async def query_transaction(
    transaction_id: str,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> TransactionResponse:
    """Return a persisted transaction or a 404 response."""

    transaction = await get_transaction(session, transaction_id)
    if transaction is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="transaction not found")
    return TransactionResponse.model_validate(transaction)


@router.get(
    "/v1/transactions/{transaction_id}/risk", response_model=RiskAssessmentResponse
)
async def query_risk(
    transaction_id: str,
    response: Response,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> RiskAssessmentResponse:
    """Return current risk state, including pending/processing as 202."""

    assessment = await get_risk_assessment(session, transaction_id)
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="risk not found")
    if assessment.status in {"pending", "processing"}:
        response.status_code = status.HTTP_202_ACCEPTED
    return RiskAssessmentResponse.model_validate(assessment)


@router.get("/v1/risks/high", response_model=HighRiskResponse)
async def query_high_risk(
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> HighRiskResponse:
    """Return a deterministic, bounded page of high-risk results."""

    if not 1 <= limit <= 100 or offset < 0:
        raise HTTPException(status_code=400, detail="limit must be 1..100 and offset non-negative")
    result = await session.execute(
        select(RiskAssessment)
        .where(RiskAssessment.level == "HIGH", RiskAssessment.status == "completed")
        .order_by(desc(RiskAssessment.score), RiskAssessment.transaction_id)
        .offset(offset)
        .limit(limit)
    )
    items = [RiskAssessmentResponse.model_validate(item) for item in result.scalars().all()]
    return HighRiskResponse(items=items, limit=limit, offset=offset)

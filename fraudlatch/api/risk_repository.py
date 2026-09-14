"""Persistence operations for risk results and processing audit events."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fraudlatch.db.models import ProcessingEvent, RiskAssessment
from fraudlatch.risk.models import RiskDecision


async def get_risk_assessment(session: AsyncSession, transaction_id: str) -> RiskAssessment | None:
    result = await session.execute(
        select(RiskAssessment).where(RiskAssessment.transaction_id == transaction_id)
    )
    return result.scalar_one_or_none()


async def persist_risk_result(
    session: AsyncSession,
    *,
    transaction_id: str,
    event_id: str,
    attempt: int,
    decision: RiskDecision,
) -> RiskAssessment:
    """Upsert the current result and append its attempt audit row in one transaction."""

    assessment = await get_risk_assessment(session, transaction_id)
    if assessment is None:
        assessment = RiskAssessment(transaction_id=transaction_id)
        session.add(assessment)
    assessment.status = "completed"
    assessment.score = decision.risk_score
    assessment.level = decision.risk_level
    assessment.reasons = [reason.model_dump(mode="json") for reason in decision.reasons]
    assessment.engine_version = decision.engine_version
    assessment.attempts = attempt
    assessment.error_code = None
    session.add(
        ProcessingEvent(
            event_id=event_id,
            transaction_id=transaction_id,
            event_type="risk.assessed",
            attempt=attempt,
            status="completed",
        )
    )
    await session.flush()
    return assessment


async def persist_risk_failure(
    session: AsyncSession,
    *,
    transaction_id: str,
    event_id: str,
    attempt: int,
    error_code: str,
) -> RiskAssessment:
    """Store a safe terminal failure without exposing exception details."""

    assessment = await get_risk_assessment(session, transaction_id)
    if assessment is None:
        assessment = RiskAssessment(transaction_id=transaction_id)
        session.add(assessment)
    assessment.status = "failed"
    assessment.attempts = attempt
    assessment.error_code = error_code
    session.add(
        ProcessingEvent(
            event_id=event_id,
            transaction_id=transaction_id,
            event_type="risk.assessed",
            attempt=attempt,
            status="failed",
            error_code=error_code,
        )
    )
    await session.flush()
    return assessment

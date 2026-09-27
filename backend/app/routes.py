from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.providers.triage.factory import build_triage_provider
from app.repositories import ComplaintRepository
from app.redis_client import get_redis
from app.redis_services import ComplaintRateLimiter, TriageCache
from app.schemas import ComplaintCreate, ComplaintResponse
from app.services import ComplaintService

router = APIRouter(prefix="/api")


@router.post("/complaints", response_model=ComplaintResponse, status_code=status.HTTP_201_CREATED)
async def create_complaint(request: Request, payload: ComplaintCreate, session: AsyncSession = Depends(get_session)):
    limiter = ComplaintRateLimiter(get_redis())
    limit_result = await limiter.check(request.client.host if request.client else "unknown")
    if not limit_result.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Complaint submission rate limit exceeded",
            headers={"Retry-After": str(limit_result.retry_after)},
        )
    service = ComplaintService(
        ComplaintRepository(session),
        build_triage_provider(get_settings()),
        TriageCache(get_redis()),
    )
    return await service.submit(payload)


@router.get("/complaints/{complaint_id}", response_model=ComplaintResponse)
async def get_complaint(complaint_id: UUID, session: AsyncSession = Depends(get_session)):
    complaint = await ComplaintRepository(session).get(complaint_id)
    if complaint is None:
        raise HTTPException(status_code=404, detail="Complaint not found")
    return complaint

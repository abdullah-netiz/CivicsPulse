from time import perf_counter
import logging

from app.models import Complaint, Status
from app.providers.triage.base import TriageProvider
from app.repositories import ComplaintRepository
from app.redis_services import TriageCache
from app.schemas import ComplaintCreate

logger = logging.getLogger(__name__)


class ComplaintService:
    def __init__(self, repository: ComplaintRepository, provider: TriageProvider, cache: TriageCache | None = None):
        self.repository = repository
        self.provider = provider
        self.cache = cache

    async def submit(self, payload: ComplaintCreate) -> Complaint:
        started = perf_counter()
        provider_name = self.provider.name
        result = None
        if self.cache:
            try:
                result = await self.cache.get(payload.text, payload.location)
            except Exception as error:
                logger.warning("Triage cache read failed: error=%s", type(error).__name__)
        if result is None:
            try:
                result = await self.provider.triage(payload.text, payload.location)
                if self.cache:
                    try:
                        await self.cache.set(payload.text, payload.location, result)
                    except Exception as error:
                        logger.warning("Triage cache write failed: error=%s", type(error).__name__)
            except Exception:
                from app.providers.triage.rules import RuleBasedTriage

                logger.warning("Triage fallback activated: provider=%s", provider_name)
                result = await RuleBasedTriage().triage(payload.text, payload.location)
                provider_name = "rules:fallback"
        else:
            provider_name = f"{provider_name}:cache"
        latency_ms = round((perf_counter() - started) * 1000)
        complaint = Complaint(
            text=payload.text,
            location=payload.location,
            reporter_contact=payload.reporter_contact,
            category=result.category,
            priority=result.priority,
            status=Status.OPEN,
            ai_summary=result.summary,
            triaged_by=provider_name,
            triage_latency_ms=latency_ms,
        )
        return await self.repository.create(complaint)

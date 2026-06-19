import hashlib
from typing import Optional, Sequence

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.work import Work
from app.schemas.job import ParsedVacancy


class VacancyRepository:
    def __init__(self, session: AsyncSession):
        """Initialize with an injected database session."""
        self.session = session

    def _generate_external_id(self, url: str) -> str:
        """Generate a unique identifier from the vacancy URL using SHA-256."""
        return hashlib.sha256(url.encode("utf-8")).hexdigest()

    async def upsert(self, vacancy_data: ParsedVacancy) -> Optional[Work]:
        """Insert a new vacancy or ignore if external_id already exists.
        Returns the Work instance on insert, None on conflict.
        """
        external_id = self._generate_external_id(vacancy_data.url)

        description_snippet = None
        if vacancy_data.description:
            description_snippet = vacancy_data.description[:500]

        stmt = insert(Work).values(
            external_id=external_id,
            title=vacancy_data.title,
            company=vacancy_data.company,
            location=vacancy_data.location,
            salary_min=vacancy_data.salary_min,
            salary_max=vacancy_data.salary_max,
            salary_currency="USD",
            skills=vacancy_data.skills,
            description_snippet=description_snippet,
            source_url=vacancy_data.url,
        )

        stmt = stmt.on_conflict_do_nothing(index_elements=["external_id"]).returning(Work)

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_unnotified(self, limit: int = 50) -> Sequence[Work]:
        """Return vacancies that have not yet been sent to Slack, ordered by creation time."""
        stmt = (
            select(Work)
            .where(Work.notified.is_(False))
            .order_by(Work.created_at.asc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def mark_notified(self, vacancy_id: int) -> None:
        """Mark a vacancy as notified in the database."""
        stmt = update(Work).where(Work.id == vacancy_id).values(notified=True)
        await self.session.execute(stmt)

    async def get_by_external_id(self, external_id: str) -> Optional[Work]:
        """Look up a vacancy by its external_id."""
        stmt = select(Work).where(Work.external_id == external_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

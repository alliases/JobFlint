import json

import structlog
from pydantic import ValidationError
from taskiq import Context, TaskiqDepends

from app.broker import broker
from app.clients import SerperClient
from app.config import get_settings
from app.db.repository import VacancyRepository
from app.db.session import get_session
from app.schemas.job import ParsedVacancy
from app.services import DedupService, FilterEngine, strip_noise

logger = structlog.get_logger()


@broker.task(task_name="extract_vacancy")
async def extract_vacancy(
    url: str,
    context: Context = TaskiqDepends(),  # noqa: B008
) -> dict[str, object]:
    """Run the full pipeline: dedup → fetch → clean → LLM parse → filter → DB store."""
    log = logger.bind(url=url)
    log.info("extract_vacancy_pipeline_started")

    settings = get_settings()

    # --- Dedup (shared Redis from TaskiqState) ---
    redis_client = context.state.redis_client
    dedup = DedupService(redis_client, ttl=settings.dedup_ttl_seconds)
    if await dedup.is_duplicate(url):
        log.info("vacancy_skipped_duplicate_redis")
        return {"status": "duplicate", "vacancy_id": None}

    # --- Fetch page content ---
    serper = SerperClient(api_key=settings.serper_api_key.get_secret_value())
    try:
        raw_text = await serper.view(url=url)
        if not raw_text:
            log.warning("empty_page_content")
            return {"status": "error", "vacancy_id": None}
    except Exception as e:
        log.error("serper_view_failed", error=str(e))
        return {"status": "error", "vacancy_id": None}
    finally:
        await serper.close()

    # --- Clean noise ---
    cleaned_text = strip_noise(raw_text)

    # --- LLM extraction ---
    llm_router = context.state.llm_router
    raw_json = await llm_router.extract_job_data(cleaned_text)

    if not raw_json:
        log.error("llm_extraction_failed")
        return {"status": "error", "vacancy_id": None}

    # --- Validate ---
    try:
        raw_dict = json.loads(raw_json)
        raw_dict["url"] = url
        parsed_vacancy = ParsedVacancy.model_validate(raw_dict)
    except (ValidationError, json.JSONDecodeError) as e:
        log.error("validation_failed", error=str(e), raw_json=raw_json)
        return {"status": "error", "vacancy_id": None}

    # --- Filter ---
    filter_engine = FilterEngine(
        keywords=settings.filter_keywords,
        location=settings.filter_location,
        salary_min=settings.filter_salary_min,
    )
    if not filter_engine.passes(parsed_vacancy):
        log.info("vacancy_skipped_by_filters")
        return {"status": "filtered", "vacancy_id": None}

    # --- Store ---
    async with get_session() as session:
        repo = VacancyRepository(session)
        vacancy = await repo.upsert(parsed_vacancy)

        if not vacancy:
            log.info("vacancy_duplicate_in_db")
            return {"status": "duplicate_db", "vacancy_id": None}

        log.info("vacancy_stored_successfully", vacancy_id=vacancy.id)
        return {"status": "stored", "vacancy_id": vacancy.id}

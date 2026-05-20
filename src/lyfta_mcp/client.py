"""Lyfta API client."""

from os import wait
import httpx

from .config import Settings
from .exceptions import (
    LyftaAuthError,
    LyftaNetworkError,
    LyftaNotFoundError,
    LyftaRateLimitError,
    LyftaResponseError,
    LyftaServerError,
)
from .models import (
    ExerciseProgressResponse,
    ExercisesResponse,
    WorkoutsResponse,
    WorkoutsSummariesResponse
)
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
    before_sleep_log,
    RetryCallState
)
import logging
import random

log = logging.getLogger(__name__)

def wait_for_lyfta(retry_state: RetryCallState) -> float:
    """Wait based on Retry-After if the server told us, else exponential jitter."""
    exception = retry_state.outcome.exception() if retry_state.outcome else None
    
    # Server-directed wait - respect Retry-After header
    if isinstance(exception, LyftaRateLimitError) and exception.retry_after_seconds:
        # Add a tiny bit of jitter to avoid synchronized retries from many clients
        jitter = random.uniform(0, 1)  # Add up to 1 second of random jitter
        wait = exception.retry_after_seconds + jitter
        log.info(f"Rate limited. Waiting {wait:.1f}s as instructed by server.")
        return min(wait, 120)
    
    # Default exponential backoff with jitter
    attempt = retry_state.attempt_number
    base = min(2 ** (attempt - 1), 30)  # 1, 2, 4, 8, 16, 30...
    return base + random.uniform(0, 1)  # Add up to 1 second of random jitter


class LyftaClient:
    """Async client for the Lyfta fitness app API."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._http = httpx.AsyncClient(
            base_url=settings.lyfta_base_url,
            headers={"Authorization": f"Bearer {settings.lyfta_api_key}"},
            timeout=settings.request_timeout_seconds,
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "LyftaClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    @retry(
        retry=retry_if_exception_type(
            (LyftaNetworkError, LyftaRateLimitError, LyftaServerError)
        ),
        wait=wait_for_lyfta,
        stop=stop_after_attempt(4),
        before_sleep=before_sleep_log(log, logging.WARNING),
        reraise=True,
    )
    async def _get(self, path: str, params: dict | None = None) -> dict:
        """Internal GET helper. Translates HTTP failures to typed errors."""
        try:
            response = await self._http.get(path, params=params)
        except httpx.TimeoutException as e:
            raise LyftaNetworkError(f"Request to {path} timed out") from e
        except httpx.HTTPError as e:
            raise LyftaNetworkError(f"Network error calling {path}: {e}") from e

        # We have a response. Check the status.
        status = response.status_code

        if 200 <= status < 300:
            try:
                data = response.json()
            except ValueError as e:
                raise LyftaResponseError(
                    f"Got {status} from {path} but body was not JSON"
                ) from e

            # Lyfta quirk: 200 OK with status=False means error in body
            if isinstance(data, dict) and data.get("status") is False:
                message = data.get("message", "Lyfta returned status=False")
                if "api key" in message.lower() or "unauthorized" in message.lower():
                    raise LyftaAuthError(message)
                raise LyftaResponseError(f"Lyfta error: {message}")

            return data

        if status == 401 or status == 403:
            raise LyftaAuthError(
                f"Auth failed ({status}) for {path}. Check your LYFTA_API_KEY."
            )
        if status == 404:
            raise LyftaNotFoundError(f"Not found: {path} (params={params})")
        if status == 429:
            retry_after = response.headers.get("Retry-After")
            retry_seconds = float(retry_after) if retry_after else None
            raise LyftaRateLimitError(
                f"Rate limited on {path}",
                retry_after_seconds=retry_seconds,
            )
        if 500 <= status < 600:
            raise LyftaServerError(f"Lyfta server error {status} on {path}")

        # Anything else (3xx, weird 4xx) — surface generically
        raise LyftaResponseError(f"Unexpected status {status} on {path}")

    async def list_workouts(self, limit: int = 10, page: int = 1) -> WorkoutsResponse:
        """Fetch full workout list with exercises and sets."""
        data = await self._get(
            "/api/v1/workouts",
            params={"limit": limit, "page": page},
        )
        return WorkoutsResponse.model_validate(data)

    async def get_workout_summary(self, limit: int = 100, page: int = 1) -> WorkoutsSummariesResponse:
        """Fetch lightweight workout summary list (no exercise/set details)."""
        data = await self._get(
            "/api/v1/workouts/summary",
            params={"limit": limit, "page": page},
        )
        return WorkoutsSummariesResponse.model_validate(data)
    
    async def list_performed_exercises(
        self, limit: int = 100, page: int = 1
    ) -> ExercisesResponse:
        """List exercises the user has performed across all workouts."""
        data = await self._get(
            "/api/v1/exercises",
            params={"limit": limit, "page": page},
        )

        # Filter out catalog entries with null IDs — Lyfta sometimes returns
        # ghost entries we can't act on.
        raw_exercises = data.get("exercises", [])
        filtered = [ex for ex in raw_exercises if ex.get("id") is not None]
        dropped = len(raw_exercises) - len(filtered)
        if dropped:
            log.warning(f"Dropped {dropped} catalog entries with null id")
        data["exercises"] = filtered

        return ExercisesResponse.model_validate(data)
    
    async def get_exercise_progress(
    self, exercise_id: int, duration_days: int = 365
    ) -> ExerciseProgressResponse:
        """Get daily progress data for one exercise over the last N days."""
        data = await self._get(
            "/api/v1/exercises/progress",
            params={"exercise_id": exercise_id, "duration": duration_days},
        )
        return ExerciseProgressResponse.model_validate(data)
"""Data transformations and compositions over Lyfta API data.

This module knows about typed Lyfta models but does not know about HTTP
or MCP. It takes typed data in and produces typed data out.
"""

from datetime import datetime, timedelta, timezone

from .client import LyftaClient
from .models import LyftaModel
import logging

log = logging.getLogger(__name__)

class ExerciseHistoryEntry(LyftaModel):
    """One performed set of one exercise, in chronological context."""

    workout_id: int
    workout_title: str
    workout_date: str # raw "YYYY-MM-DD HH:MM:SS" UTC
    set_number: int  # 1-indexed within the exercise
    weight: float | None
    reps: int | None
    is_completed: bool
    
def _parse_workout_date(raw: str) -> datetime:
    """Parse Lyfta's 'YYYY-MM-DD HH:MM:SS' as UTC."""
    # Lyfta dates are in UTC, so we parse as naive and then set tzinfo to UTC
    dt_naive = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
    return dt_naive.replace(tzinfo=timezone.utc)

async def get_exercise_history(
    client: LyftaClient,
    exercise_id: int,
    duration_days: int = 365,
    page_size: int = 100,
) -> list[ExerciseHistoryEntry]:
    """All sets of one exercise within a recent time window.

    Composes data from /api/v1/workouts (which has full set detail) by
    paginating most-recent-first and bailing out once we hit workouts
    older than the requested window.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=duration_days)
    results: list[ExerciseHistoryEntry] = []
    page = 1
    
    while True:
        response = await client.list_workouts(limit=page_size, page=page)
        workouts = response.workouts
        log.info(f"get_exercise_history: page={page}, fetched={len(workouts)}, results_so_far={len(results)}")

        if not workouts:
            break  # no more data
        
        should_stop = False # assumes Lyfta returns workouts most-recent-first; verified empirically.
        for workout in workouts:
            workout_dt = _parse_workout_date(workout.workout_perform_date)
            if workout_dt < cutoff:
                should_stop = True
                break  # this workout is older than cutoff; rest of page is older too

            for exercise in workout.exercises:
                if exercise.exercise_id != exercise_id:
                    continue
                for set_idx, s in enumerate(exercise.sets, start=1):
                    results.append(ExerciseHistoryEntry(
                        workout_id=workout.id,
                        workout_title=workout.title,
                        workout_date=workout.workout_perform_date,
                        set_number=set_idx,
                        weight=s.weight,
                        reps=s.reps,
                        is_completed=s.is_completed,
                    ))
        if should_stop:
            log.info(f"get_exercise_history: bailed out at page={page}, cutoff={cutoff.date()}")
            break
        
        page += 1
    
    log.info(f"get_exercise_history: done, {len(results)} sets found for exercise_id={exercise_id}")
    return results
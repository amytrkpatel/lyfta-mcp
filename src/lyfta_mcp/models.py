"""Pydantic models for Lyfta API responses.

Models are organized bottom-up: leaves first (Set), then parents (Exercise, Workout), then envelopes (WorkoutsResponse). This mirrors how the data is composed.
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LyftaModel(BaseModel):
    """Base for all Lyfta models. Centralizes common config."""
    
    model_config = ConfigDict(
        populate_by_name=True,  # accept both alias and field name
        extra="ignore", #ignore unknown fields silently
        str_strip_whitespace=True, #strip whitespace from strings
    )

class Set(LyftaModel):
    """One performed set within an exercise."""

    id: str = "0"                          # was strict str — now defaults for placeholders
    weight: float | None = None            # was float=0.0 — now nullable for placeholders
    reps: int | None = None                # was int=0 — now nullable for placeholders
    rir: str | None = None
    duration: str | None = None            # changed from float — Lyfta sends "6:17" sometimes
    distance: str | None = None            # changed from float — same reason
    set_type_id: str = "0"
    is_completed: bool = False
    record_type: str | None = None
    record_level: str | None = None
    record_value: str | None = None        # confirm this is str, not float
    
    @field_validator(
        "rir", "record_type", "record_level", "record_value",
        "duration", "distance", "weight", "reps",
        mode="before"
    )
    @classmethod
    def normalize_empty_to_none(cls, v):
        """Lyfta sometimes sends '', 'null', 'None' as strings instead of JSON null."""
        if isinstance(v, str) and v.strip().lower() in ("", "null", "none"):
            return None
        return v

    @field_validator("id", "set_type_id", mode="before")
    @classmethod
    def coerce_to_string(cls, v):
        """Lyfta sometimes sends integers where it should send strings (e.g., id=0)."""
        if v is None:
            return "0"
        return str(v)

class Exercise(LyftaModel):
    """One exercise within a workout (or standalone from /api/v1/exercises).   """
    
    exercise_id: int
    exercise_name: str = Field(alias="excercise_name")
    exercise_type: str | None = None
    exercise_image: str | None = None
    exercise_rest_time: int | None = None
    sets: list[Set] = Field(default_factory=list)

class User(LyftaModel):
    """Reference to the user who performed the workout."""
    
    username: str

class Workout(LyftaModel):
    """One performed workout session with all its exercises and sets."""
    
    id: int
    title: str
    body_weight: float = 0.0
    workout_perform_date: str
    total_volume: float = 0.0
    total_lifted_weight: float = Field(default=0.0, alias="totalLiftedWeight")
    user: User | None = None
    exercises: list[Exercise] = Field(default_factory=list)

class PaginatedEnvelope(LyftaModel):
    """Common pagination metadata returned by Lyfta list endpoints."""

    status: bool
    count: int
    total_records: int | None = None
    total_pages: int | None = None
    current_page: int | None = None
    limit: int

    @field_validator("current_page", "total_pages", "total_records", mode="before")
    @classmethod
    def normalize_optional_int(cls, v):
        """Lyfta sometimes returns null or empty strings for pagination fields."""
        if v is None:
            return None
        if isinstance(v, str):
            value = v.strip()
            if value.lower() in ("", "null", "none"):
                return None
            try:
                return int(value)
            except ValueError:
                return None
        return v

class WorkoutsResponse(PaginatedEnvelope):
    """Envelope for /api/v1/workouts response."""
    workouts: list[Workout] = Field(default_factory=list)

class WorkoutSummary(LyftaModel):
    """Lightweight workout record from /api/v1/workouts/summary."""
    
    id: str
    title: str
    description: str | None = None
    workout_duration: str | None = None
    total_volume: float = 0.0
    workout_perform_date: str
    
    @field_validator("id", mode="before")
    @classmethod
    def coerce_id_to_str(cls, v):
        if v is None:
            raise ValueError("WorkoutSummary id cannot be null")
        return str(v)
    
    @field_validator("total_volume", mode="before")
    @classmethod
    def null_volume_is_zero(cls, v):
        """Bodyweight workouts come back with null volume; treat as 0."""
        if v is None:
            return 0.0
        if isinstance(v, str) and v.strip().lower() in ("", "null", "none"):
            return 0.0
        return v

class WorkoutsSummariesResponse(PaginatedEnvelope):
    """Envelope for /api/v1/workouts/summary response."""

    workouts: list[WorkoutSummary] = Field(default_factory=list)



class ExerciseCatalogItem(LyftaModel):
    """One exercise from /api/v1/exercises — a definition, not a performance."""

    id: str
    name: str
    image_url: str | None = Field(default=None, alias="image_name")
    equipment_id: str | None = None
    body_part_id: str | None = None
    target_muscles_id: str | None = Field(default=None, alias="Target_muscles_id")
    synergist_muscles_id: str | None = Field(default=None, alias="Synergist_muscles_id")
    exercise_type: str | None = None

class ExercisesResponse(PaginatedEnvelope):
    """Envelope for /api/v1/exercises response."""

    exercises: list[ExerciseCatalogItem] = Field(default_factory=list)

class ExerciseProgress(LyftaModel):
    """Daily best performance for one exercise, from /api/v1/exercises/progress."""

    date: str                              # YYYY-MM-DD; keep raw for now
    best_weight: float | None = None       # in weight_unit (e.g. kg)
    best_reps: int | None = None
    best_volume: float | None = None
    estimated_rm: float | None = None      # coerced from string in wire

# TODO: if Lyfta returns 'null' string for any of these fields, add normalize validator
class ExerciseProgressResponse(LyftaModel):
    """Envelope for /api/v1/exercises/progress response."""

    status: bool
    weight_unit: str                       # "kg" or "lb"
    data: list[ExerciseProgress] = Field(default_factory=list)


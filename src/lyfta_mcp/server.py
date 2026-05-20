"""MCP server entry point.

Supports two transports selected via TRANSPORT env var:
  stdio (default) — Claude Desktop subprocess mode
  http            — Hosted mode for Railway/Render, accessible from any Claude client
"""

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.fastmcp import FastMCP

from .client import LyftaClient
from .config import Settings
from .exceptions import LyftaError
from .transforms import get_exercise_history

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("lyfta_mcp")


# ─── Client lifecycle ────────────────────────────────────────────────────────

_client: LyftaClient | None = None


async def get_client() -> LyftaClient:
    """Return the shared LyftaClient, initializing if needed."""
    global _client
    if _client is None:
        settings = Settings.from_env()
        _client = LyftaClient(settings)
        await _client.__aenter__()
        log.info("LyftaClient initialized")
    return _client


# ─── MCP server ──────────────────────────────────────────────────────────────

mcp = FastMCP(
    "lyfta-mcp",
    stateless_http=True,
    host="0.0.0.0",
    port=int(os.environ.get("PORT", "8000")),
)


# ─── Tools ───────────────────────────────────────────────────────────────────

@mcp.tool(description=(
    "Get recent workout sessions with FULL exercise and set details. "
    "Use this when the user asks about what exercises they did, weights "
    "lifted, sets/reps performed, or wants to inspect specific workouts. "
    "Returns up to 100 workouts per call, most recent first. Each workout "
    "includes title, date (UTC), total volume, exercises performed, and "
    "individual set data (weight, reps, completion). Use page parameter "
    "to fetch older workouts."
))
async def list_workouts(limit: int = 10, page: int = 1) -> str:
    client = await get_client()
    try:
        response = await client.list_workouts(limit=limit, page=page)
        return response.model_dump_json(indent=2)
    except LyftaError as e:
        return json.dumps({"error": type(e).__name__, "message": str(e)})


@mcp.tool(description=(
    "Get a LIGHTWEIGHT list of recent workouts (no exercise/set details). "
    "Prefer this over list_workouts when the user only needs an overview "
    "of which workouts happened, dates, durations, and total volume. "
    "Much cheaper than list_workouts. Returns up to 1000 workouts per call.\n\n"
    "IMPORTANT: workouts older than late 2024 may show volume=0 and "
    "duration='00:00:00' — these are real workouts imported from another "
    "app (e.g., Strong) via CSV, where volume/duration metadata wasn't "
    "preserved. This is NOT a bug — don't switch to list_workouts to fix it."
))
async def get_workout_summary(limit: int = 100, page: int = 1) -> str:
    client = await get_client()
    try:
        response = await client.get_workout_summary(limit=limit, page=page)
        return response.model_dump_json(indent=2)
    except LyftaError as e:
        return json.dumps({"error": type(e).__name__, "message": str(e)})


@mcp.tool(description=(
    "Get the catalog of exercises the user has logged across all workouts. "
    "Use this to look up an exercise's ID by name (needed for "
    "get_exercise_progress and get_exercise_history), or to see what "
    "exercises have been performed at least once. Returns id, name, image "
    "URL, and exercise type. Does NOT include performance data."
))
async def list_performed_exercises(limit: int = 100, page: int = 1) -> str:
    client = await get_client()
    try:
        response = await client.list_performed_exercises(limit=limit, page=page)
        return response.model_dump_json(indent=2)
    except LyftaError as e:
        return json.dumps({"error": type(e).__name__, "message": str(e)})


@mcp.tool(description=(
    "Get strength progress over time for ONE specific exercise. "
    "Returns daily best performance: best weight lifted, best reps, "
    "best volume, and estimated 1-rep-max. Use this for questions like "
    "'how is my bench press progressing?' or 'show my squat 1RM trend'. "
    "First look up the exercise ID using list_performed_exercises. "
    "Data is sparse — one entry per day the exercise was performed."
))
async def get_exercise_progress(exercise_id: int, duration_days: int = 365) -> str:
    client = await get_client()
    try:
        response = await client.get_exercise_progress(
            exercise_id=exercise_id,
            duration_days=duration_days,
        )
        return response.model_dump_json(indent=2)
    except LyftaError as e:
        return json.dumps({"error": type(e).__name__, "message": str(e)})


@mcp.tool(description=(
    "Get detailed per-set history for ONE specific exercise — every set "
    "logged, with weight, reps, and date. Use this when the user wants "
    "granular session-level detail: 'show me every bench press set I've "
    "done', 'how has my working weight changed over time'. Returns a flat "
    "list of sets with workout context (date, workout name, set number).\n\n"
    "Note: is_completed is often False even for sets that were performed — "
    "this field wasn't reliably populated, so don't use it to filter.\n\n"
    "Prefer get_exercise_progress for a high-level 1RM trend. "
    "Requires exercise_id — use list_performed_exercises first."
))
async def get_exercise_history_tool(
    exercise_id: int,
    duration_days: int = 365,
) -> str:
    client = await get_client()
    try:
        entries = await get_exercise_history(
            client=client,
            exercise_id=exercise_id,
            duration_days=duration_days,
        )
        return json.dumps([e.model_dump() for e in entries], indent=2)
    except LyftaError as e:
        return json.dumps({"error": type(e).__name__, "message": str(e)})


# ─── Entry point ─────────────────────────────────────────────────────────────

def main() -> None:
    transport = os.environ.get("TRANSPORT", "stdio")
    log.info(f"Starting Lyfta MCP server (transport={transport})")

    if transport == "http":
        log.info(f"HTTP transport on port {os.environ.get('PORT', '8000')}")
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
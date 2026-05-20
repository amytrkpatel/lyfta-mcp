"""MCP server entry point — Stage 2: real Lyfta tools."""

import asyncio
import json
import logging
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from .client import LyftaClient
from .config import Settings
from .exceptions import LyftaError
from .transforms import get_exercise_history

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("lyfta_mcp")

server = Server("lyfta-mcp")

# Module-level client — initialized in main(), shared across all tool calls.
_client: LyftaClient | None = None


@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    """Tell Claude what tools we expose."""
    return [
        Tool(
            name="list_workouts",
            description=(
                "Get recent workout sessions with FULL exercise and set details. "
                "Use this when the user asks about what exercises they did, weights "
                "lifted, sets/reps performed, or wants to inspect specific workouts. "
                "Returns up to 100 workouts per call, most recent first. Each workout "
                "includes title, date (UTC), total volume, exercises performed, and "
                "individual set data (weight, reps, completion). Use page parameter "
                "to fetch older workouts."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Number of workouts to fetch (max 100)",
                        "minimum": 1,
                        "maximum": 100,
                        "default": 10,
                    },
                    "page": {
                        "type": "integer",
                        "description": "Page number, 1-indexed (1 = most recent)",
                        "minimum": 1,
                        "default": 1,
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="get_workout_summary",
            description=(              # ← REPLACE THE TEXT INSIDE THIS ONE
                "Get a LIGHTWEIGHT list of recent workouts (no exercise/set details). "
                "Prefer this over list_workouts when the user only needs an overview "
                "of which workouts happened, dates, durations, and total volume — not "
                "the inner exercise data. Much cheaper than list_workouts. Returns up "
                "to 1000 workouts per call.\n\n"
                "IMPORTANT: workouts older than late 2024 may show volume=0 and "
                "duration='00:00:00' — these are real workouts imported from another "
                "app (e.g., Strong) via CSV, where volume/duration metadata wasn't "
                "preserved. This is NOT a bug or a sort issue — these workouts are "
                "real and in correct chronological order. Don't switch to list_workouts "
                "to 'fix' this; it can't recover the missing metadata either."
            ),

            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Number of workouts to fetch (max 1000)",
                        "minimum": 1,
                        "maximum": 1000,
                        "default": 100,
                    },
                    "page": {
                        "type": "integer",
                        "description": "Page number, 1-indexed",
                        "minimum": 1,
                        "default": 1,
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="list_performed_exercises",
            description=(
                "Get the catalog of exercises the user has logged across all workouts. "
                "Use this to look up an exercise's ID by name (needed for the "
                "get_exercise_progress tool), or to see what exercises have been "
                "performed at least once. Returns id, name, image URL, and exercise "
                "type ('weight_reps' or 'duration'). Does NOT include performance "
                "data like volume or frequency — for that, use list_workouts."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Max exercises to fetch",
                        "minimum": 1,
                        "maximum": 200,
                        "default": 100,
                    },
                    "page": {
                        "type": "integer",
                        "description": "Page number, 1-indexed",
                        "minimum": 1,
                        "default": 1,
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="get_exercise_progress",
            description=(
                "Get strength progress over time for ONE specific exercise. "
                "Returns daily best performance: best weight lifted, best reps, "
                "best volume, and estimated 1-rep-max. Use this for questions like "
                "'how is my bench press progressing?' or 'show my squat 1RM trend'. "
                "First, look up the exercise's ID using list_performed_exercises if "
                "you don't have it. Data is sparse — one entry per day the exercise "
                "was performed (not daily continuous)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "exercise_id": {
                        "type": "integer",
                        "description": "The exercise ID (use list_performed_exercises to find it by name)",
                    },
                    "duration_days": {
                        "type": "integer",
                        "description": "How many days back to look. Default 365 = last year. Use 3650 for full history.",
                        "minimum": 1,
                        "maximum": 3650,
                        "default": 365,
                    },
                },
                "required": ["exercise_id"],
            },
        ),
        Tool(
            name="get_exercise_history",
            description=(
                "Get detailed per-set history for ONE specific exercise — every set "
                "logged, with weight, reps, and date. Use this when the user wants "
                "granular session-level detail: 'show me every bench press set I've "
                "done', 'how has my working weight changed over time', 'what rep ranges "
                "am I hitting'. Returns a flat list of sets, most recent first, with "
                "workout context (date, workout name, set number). "
                "Note: is_completed is often False even for sets that were performed — "
                "this field wasn't reliably populated, so don't use it to filter.\n\n"
                "Prefer get_exercise_progress for a high-level 1RM trend. Use this "
                "tool when the user wants the raw set data behind that trend.\n\n"
                "Requires exercise_id — use list_performed_exercises first if you "
                "don't have it."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "exercise_id": {
                        "type": "integer",
                        "description": "Exercise ID (use list_performed_exercises to find by name)",
                    },
                    "duration_days": {
                        "type": "integer",
                        "description": "How many days back to look. Default 180 (~6 months). Use 3650 for full history.",
                        "minimum": 1,
                        "maximum": 3650,
                        "default": 365,
                    },
                },
                "required": ["exercise_id"],
            },
        ),
    ]


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Execute a tool call from Claude."""
    log.info(f"Tool called: {name} with arguments: {arguments}")

    if _client is None:
        raise RuntimeError("Lyfta client not initialized")

    try:
        if name == "list_workouts":
            response = await _client.list_workouts(
                limit=arguments.get("limit", 10),
                page=arguments.get("page", 1),
            )
            return [TextContent(type="text", text=response.model_dump_json(indent=2))]

        if name == "get_workout_summary":
            response = await _client.get_workout_summary(
                limit=arguments.get("limit", 100),
                page=arguments.get("page", 1),
            )
            return [TextContent(type="text", text=response.model_dump_json(indent=2))]

        if name == "list_performed_exercises":
            response = await _client.list_performed_exercises(
                limit=arguments.get("limit", 100),
                page=arguments.get("page", 1),
            )
            return [TextContent(type="text", text=response.model_dump_json(indent=2))]

        if name == "get_exercise_progress":
            response = await _client.get_exercise_progress(
                exercise_id=arguments["exercise_id"],
                duration_days=arguments.get("duration_days", 365),
            )
            return [TextContent(type="text", text=response.model_dump_json(indent=2))]

        if name == "get_exercise_history":
            entries = await get_exercise_history(
                client=_client,
                exercise_id=arguments["exercise_id"],
                duration_days=arguments.get("duration_days", 365),
            )
            payload = [e.model_dump() for e in entries]
            return [TextContent(type="text", text=json.dumps(payload, indent=2))]

        raise ValueError(f"Unknown tool: {name}")

    except LyftaError as e:
        log.exception(f"Lyfta call failed in tool {name}")
        return [
            TextContent(
                type="text",
                text=json.dumps({
                    "error": type(e).__name__,
                    "message": str(e),
                }),
            )
        ]


async def main() -> None:
    global _client
    settings = Settings.from_env()
    log.info("Starting Lyfta MCP server")

    async with LyftaClient(settings) as client:
        _client = client
        try:
            async with stdio_server() as (read_stream, write_stream):
                await server.run(
                    read_stream,
                    write_stream,
                    server.create_initialization_options(),
                )
        finally:
            _client = None


if __name__ == "__main__":
    asyncio.run(main())
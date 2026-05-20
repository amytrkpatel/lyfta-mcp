# Lyfta MCP

An asyncronous [Model Context Protocol](https://modelcontextprotocol.io/) server that integrates the [Lyfta fitness app](https://lyfta.app) with Claude and other AI assistants. Query your workout history, exercise progress, and performance data through natural language.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

## Background

Lyfta doesn't have a way to ask questions about your own training data. You can see charts and logs, but you can't ask "am I getting stronger?" or "what does my bench press trend look like over two years?"

This project connects Lyfta to Claude via the Model Context Protocol, turning your raw workout logs into a conversational interface. Built as a data engineering learning project — the codebase demonstrates async API clients, Pydantic data modeling, retry patterns, and MCP server architecture.

## Overview

Lyfta MCP bridges your fitness data from Lyfta with Claude's intelligence. Ask Claude questions like:
- "What was my heaviest bench press this month?"
- "Show me my squat progress over the last 6 months"
- "How many workouts did I complete last week?"
- "What's my exercise library?"

Claude uses MCP tools to fetch real-time data from Lyfta and synthesize insights, trends, and recommendations based on your actual performance.

## Features

- **Real-time fitness data access** — Fetch workouts, exercises, and progress data on demand
- **Async/await support** — Non-blocking I/O for responsive interactions
- **Robust error handling** — Typed exceptions and automatic retries with exponential backoff
- **Rate limit aware** — Respects server Retry-After headers
- **Data validation** — Pydantic models ensure API response integrity
- **Pagination support** — Efficiently handle large datasets

### Available Tools

| Tool | Purpose |
|------|---------|
| `list_workouts` | Fetch recent workouts with full exercise and set details (up to 100 per call) |
| `get_workout_summary` | Lightweight workout overview without exercise details (up to 1000 per call) |
| `list_performed_exercises` | Get your exercise catalog with names, IDs, and types |
| `get_exercise_progress` | Strength progress over time for a specific exercise (daily best) |
| `get_exercise_history` | Detailed per-set history for an exercise with chronological context |

## Installation

### Prerequisites

- Python 3.11 or higher
- A Lyfta account with API access
- Your Lyfta API key

### Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/lyfta-mcp.git
   cd lyfta-mcp
   ```

2. **Create a virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -e .
   ```

4. **Configure environment variables:**
   
   Create a `.env` file in the project root:
   ```bash
   LYFTA_API_KEY=your_api_key_here
   LYFTA_BASE_URL=https://my.lyfta.app  # Optional, defaults to production
   LYFTA_TIMEOUT=30                      # Optional, timeout in seconds
   LYFTA_MAX_RETRIES=4                   # Optional, max retry attempts
   ```

   **To obtain your API key:**
   1. Log in to [Lyfta](https://my.lyfta.app)
   2. Go to Settings → API Keys
   3. Generate a new API key and copy it to `.env`

5. **Verify installation:**
   ```bash
   python -m lyfta_mcp.server
   ```

## Usage

### Running the MCP Server

```bash
python -m lyfta_mcp.server
```

The server will start and listen on stdio for MCP requests from Claude or other compatible clients.

### With Claude Desktop

To use with Claude Desktop, add the following to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "lyfta": {
      "command": "/absolute/path/to/venv/bin/python",
      "args": ["-m", "lyfta_mcp.server"],
      "env": {
        "LYFTA_API_KEY": "your_api_key_here"
      }
    }
  }
}
```

**Important:** Replace `/absolute/path/to/venv/bin/python` with the actual path to your Python interpreter. On macOS with conda, this is typically `/Users/yourname/anaconda3/envs/your_env/bin/python`. Find it with:
```bash
which python  # after activating your venv
```

Then ask Claude questions about your fitness data!

### Programmatic Usage

```python
import asyncio
from lyfta_mcp.client import LyftaClient
from lyfta_mcp.config import Settings

async def main():
    settings = Settings.from_env()
    async with LyftaClient(settings) as client:
        # Fetch recent workouts
        response = await client.list_workouts(limit=10, page=1)
        for workout in response.workouts:
            print(f"{workout.title} on {workout.workout_perform_date}")
        
        # Get exercise catalog
        exercises = await client.list_performed_exercises(limit=50)
        print(f"Total exercises: {exercises.count}")
        
        # Get progress for bench press (example)
        progress = await client.get_exercise_progress(exercise_id=123, duration_days=365)
        for entry in progress.data:
            print(f"Date: {entry.date}, 1RM: {entry.estimated_rm}")

asyncio.run(main())
```

## Architecture

### Module Structure

```
src/lyfta_mcp/
├── __init__.py           # Package exports
├── client.py             # Async HTTP client with retry logic
├── config.py             # Environment-based configuration
├── exceptions.py         # Typed exception hierarchy
├── models.py             # Pydantic validation models
├── server.py             # MCP server entry point
└── transforms.py         # Data composition & business logic
```

### Key Components

**client.py** — `LyftaClient`
- Async HTTP wrapper around the Lyfta API
- Automatic retries with exponential backoff jitter
- Rate limit awareness (respects `Retry-After` headers)
- Translates HTTP errors into typed exceptions
- Handles Lyfta API quirks (status=False in 200 responses, missing fields, etc.)

**config.py** — `Settings`
- Immutable configuration loaded from environment variables
- Sensible defaults for base URL, timeout, and retry settings
- Runtime validation of required API key

**models.py** — Pydantic Models
- `Set`, `Exercise`, `Workout` — Core domain objects
- `WorkoutsResponse`, `ExercisesResponse` — API envelope structures
- Field normalization for Lyfta API quirks (string nulls, type coercion)
- Automatic validation on instantiation

**exceptions.py** — Exception Hierarchy
- `LyftaError` — Base exception
- `LyftaAuthError` — Authentication failures (401, 403)
- `LyftaNotFoundError` — Resource not found (404)
- `LyftaRateLimitError` — Rate limit exceeded (429), includes retry timing
- `LyftaServerError` — Server errors (5xx)
- `LyftaNetworkError` — Connection/network failures
- `LyftaResponseError` — Valid response but unusable (bad JSON, etc.)

**server.py** — MCP Server
- Registers five tools that Claude can call
- Handles tool invocation and error translation
- Manages client lifecycle (initialization, cleanup)
- Structured logging for debugging

**transforms.py** — Data Composition
- `get_exercise_history()` — Composes per-set history from paginated workout data
- Handles chronological filtering and pagination logic
- Maintains data type safety with Pydantic models

## Configuration

All configuration is loaded from environment variables (see `.env` example):

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LYFTA_API_KEY` | ✓ | — | Your Lyfta API key |
| `LYFTA_BASE_URL` | | `https://my.lyfta.app` | Lyfta API base URL |
| `LYFTA_TIMEOUT` | | `30` | Request timeout in seconds |
| `LYFTA_MAX_RETRIES` | | `4` | Max automatic retry attempts |

Load configuration with:
```python
from lyfta_mcp.config import Settings
settings = Settings.from_env()  # Raises RuntimeError if LYFTA_API_KEY is missing
```

## Error Handling

The client provides typed exceptions for graceful error handling:

```python
from lyfta_mcp.exceptions import (
    LyftaAuthError,
    LyftaRateLimitError,
    LyftaServerError,
    LyftaNetworkError,
)

try:
    response = await client.list_workouts()
except LyftaAuthError:
    print("Invalid API key")
except LyftaRateLimitError as e:
    print(f"Rate limited. Retry after {e.retry_after_seconds}s")
except LyftaServerError:
    print("Lyfta server is down")
except LyftaNetworkError:
    print("Network unreachable")
```

Automatic retries with exponential backoff are built in for:
- Network errors (`LyftaNetworkError`)
- Rate limits (`LyftaRateLimitError`)
- Server errors (`LyftaServerError`)

## Logging

Configure logging to see detailed request/response traces:

```python
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
```

Log output includes:
- HTTP request/response details
- Retry attempts and timing
- Data validation steps
- API errors and quirks

## Development

The project uses a modern Python package structure with `pyproject.toml`. Install with development dependencies:

```bash
pip install -e ".[dev]"
```

Testing and type checking are on the roadmap. Contributions welcome — see the Contributing section.

## Troubleshooting

### "LYFTA_API_KEY not set"
Ensure your `.env` file exists in the project root and contains a valid `LYFTA_API_KEY`.

### Connection timeout
Increase `LYFTA_TIMEOUT` in `.env`:
```bash
LYFTA_TIMEOUT=60
```

### Rate limit errors
The client automatically retries with exponential backoff. To adjust:
```bash
LYFTA_MAX_RETRIES=6
```

### "Lyfta returned status=False"
This is a quirk of the Lyfta API—sometimes it returns `{"status": false}` in a 200 response. The client detects and translates this to an appropriate exception.

### Missing or null fields in responses
The Pydantic models normalize Lyfta's inconsistent field formatting (string nulls, type coercion, missing metadata for imported workouts). If a field is unexpectedly absent, it may be set to a sensible default or `None`.

## Known Limitations

- **Old imported workouts** — Workouts imported from other apps (e.g., Strong CSV imports) may have missing metadata like `total_volume` or `duration`. This is not a bug; the metadata wasn't preserved during import.
- **is_completed field** — This field is often `False` even for sets that were actually performed. Don't rely on it for filtering.
- **Exercise IDs are not stable across accounts** — IDs like `exercise_id=2` are specific to your Lyfta account. Don't hardcode them; use `list_performed_exercises` to look them up by name.
- **Pagination** — The API returns results in reverse chronological order (most recent first). Use the `page` parameter to fetch older data.

## Security

- **Never commit your `.env` file or API key** to version control. It's listed in `.gitignore` by default.
- **Rotate your API key** periodically via Lyfta Settings.
- **Don't share your config** containing the API key.

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License — see the [LICENSE](./LICENSE) file for details.

## Support

- **Lyfta API Documentation** — [https://docs.lyfta.app](https://docs.lyfta.app)
- **MCP Documentation** — [https://modelcontextprotocol.io/](https://modelcontextprotocol.io/)
- **Issues** — Open an issue on GitHub for bugs or feature requests

## Acknowledgments

- Built for the [Lyfta](https://lyfta.app) fitness platform
- Uses the [Model Context Protocol](https://modelcontextprotocol.io/) for AI integration

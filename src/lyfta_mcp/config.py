"""configuration loaded from environment variables."""
import os
from dataclasses import dataclass
from dotenv import load_dotenv
from flask import request

#Load .env file into os.environ
load_dotenv()

@dataclass(frozen=True)
class Settings:
    """Immutable Settings loaded from environment variables.
    """

    lyfta_api_key: str
    lyfta_base_url: str = "https://my.lyfta.app"
    request_timeout_seconds: float = 30.0
    max_retries: int = 4
    
    @classmethod
    def from_env(cls) -> "Settings":
        api_key = os.getenv("LYFTA_API_KEY")
        if not api_key:
            raise RuntimeError(
                "LYFTA_API_KEY not set. Add it to your .env file or export it."
                )
        return cls(
            lyfta_api_key=api_key,
            lyfta_base_url=os.environ.get("LYFTA_BASE_URL", "https://my.lyfta.app"),
            request_timeout_seconds=float(os.environ.get("LYFTA_TIMEOUT", "30")),
            max_retries=int(os.environ.get("LYFTA_MAX_RETRIES", "4")),
        )
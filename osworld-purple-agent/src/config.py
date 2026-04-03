"""
Configuration for OSWorld Purple Agent.

Loads all settings from environment variables with OSWORLD_ prefix,
falling back to sensible defaults. Call dotenv_values / load_dotenv
before importing this module if running locally.
"""

import os
from dotenv import load_dotenv

load_dotenv()


class OsworldConfig:
    """Agent configuration loaded from environment variables."""

    def __init__(self) -> None:
        self.host: str = os.getenv("OSWORLD_HOST", "0.0.0.0")
        self.port: int = int(os.getenv("OSWORLD_PORT", "8000"))
        self.agent_name: str = os.getenv("OSWORLD_AGENT_NAME", "OSWorld Purple Agent")
        self.agent_version: str = os.getenv("OSWORLD_AGENT_VERSION", "0.1.0")
        self.log_level: str = os.getenv("OSWORLD_LOG_LEVEL", "INFO").upper()
        self.log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


# Module-level singleton — import and use directly.
config = OsworldConfig()

__all__ = ["OsworldConfig", "config"]

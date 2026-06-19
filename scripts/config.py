import os
import sys
import yaml
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")


def get_config() -> dict:
    with open(ROOT / "config.yaml") as f:
        return yaml.safe_load(f)


def get_client() -> tuple[OpenAI, dict]:
    cfg = get_config()["llm"]
    client = OpenAI(
        api_key=os.getenv("OPENROUTER_API_KEY", ""),
        base_url=cfg["base_url"],
    )
    return client, cfg


def wiki_dir() -> Path:
    return ROOT / get_config()["wiki"]["dir"]


def raw_dir() -> Path:
    return ROOT / get_config()["wiki"]["raw_dir"]

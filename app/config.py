import os
from pathlib import Path
import yaml
from dotenv import load_dotenv

load_dotenv()

_config = None

def load_config() -> dict:
    global _config
    if _config is None:
        cfg_path = Path(__file__).parent.parent / "config.yaml"
        with open(cfg_path) as f:
            _config = yaml.safe_load(f)
    return _config

def get_config() -> dict:
    return load_config()

def get_api_key() -> str:
    return os.environ.get("OPENROUTER_API_KEY", "")

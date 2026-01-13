import os

from dotenv import load_dotenv


load_dotenv()


def get_env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value


def get_env_int(name: str, default: int) -> int:
    value = get_env(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def get_env_float(name: str, default: float) -> float:
    value = get_env(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def get_env_bool(name: str, default: bool) -> bool:
    value = get_env(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}

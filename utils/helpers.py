import uuid
from datetime import date
from typing import Callable, Any
from utils import logger


logger = logger.get_logger(__name__)

def is_valid_uuid(uuid_to_test: str, version: int = 4) -> bool:
    try:
        # Attempt to create a UUID object
        uuid_obj = uuid.UUID(uuid_to_test, version=version)
    except ValueError:
        return False

    # Check if the string representation matches the UUID object
    # This prevents cases like '12345' being parsed as a valid UUID
    return str(uuid_obj) == uuid_to_test.lower()

def convert_string_to_uuid(string: str) -> str:
    if(not string or len(string) != 32):
        raise Exception(f"{string} cannot be massaged to UUID format")
    
    if(is_valid_uuid(string)):
        return string

    
    return f"{string[0:8]}-{string[8:12]}-{string[12:16]}-{string[16:20]}-{string[20:]}"

def parse_jellyfin_date(date_str: str):
    if not date_str:
        return None

    clean_str = f"{date_str.split('T')[0]}"
    return clean_str

def parse_watchstate_played_at(played_at):
    """Resolve a WatchState `played_at` (ISO 8601 string or Unix epoch) to a date.

    An all-digit epoch is handled explicitly: date.fromisoformat accepts the
    basic `YYYYMMDD` form on Python 3.11+, so a 10-digit epoch like 1792011209
    would otherwise be silently misread as the date 1792-01-12 instead of being
    treated as a timestamp. Returns None for empty input."""
    if not played_at:
        return None

    text = str(played_at)
    if text.isdigit():
        return date.fromtimestamp(int(text))

    return date.fromisoformat(parse_jellyfin_date(text))

def create_map_by_id(items, id_key):
    return {item[id_key]: item for item in items}

def to_int_ids(ids):
    normalized = set()
    for id in ids or []:
        if id is None:
            continue
        try:
            normalized.add(int(id))
        except (ValueError, TypeError):
            continue
    return normalized

def safe_call(func: Callable, *args: Any, **kwargs: Any) -> Any:
    """
    Executes a function safely. If it fails, logs the debug/exception 
    information and returns None without crashing the thread.
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        # logger.exception automatically captures the full stack trace
        logger.exception(f"Safe call failed for function '{func.__name__}' with args {args} and kwargs {kwargs}")
        return None


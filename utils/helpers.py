import uuid
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

def create_map_by_id(items, id_key):
    return {item[id_key]: item for item in items}

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


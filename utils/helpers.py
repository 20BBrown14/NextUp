import uuid

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



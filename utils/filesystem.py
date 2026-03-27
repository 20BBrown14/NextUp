from pathlib import Path
from typing import Union, List
import json
import shutil

def create_directory(target_path: Union[str, Path]) -> Path:
    # Convert string to a Path object if it isn't one already
    path_obj = Path(target_path).resolve()
    
    # parents=True: Creates any missing folders in the hierarchy
    # exist_ok=True: Prevents an exception if the folder already exists
    path_obj.mkdir(parents=True, exist_ok=True)
    
    return path_obj

def save_json(filepath, data):
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving JSON: {e}")

import json

def read_json(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except FileNotFoundError:
        print(f"Error: The file {filepath} was not found.")
        return None
    except json.JSONDecodeError:
        print(f"Error: Failed to decode JSON. Check if the file format is valid.")
        return None
    
def create_hard_link(src: str, dest: str) -> None:
    if not src or not dest:
        raise Exception(f"Source and destination are required! Got {src} and {dest} respectively")

    source_path = Path(src)
    dest_path = Path(dest)

    try:
        dest_path.hardlink_to(source_path)
    except FileExistsError:
        # No problemo
        return
    except OSError as e:
        if e.errno == 18: # Cross-device link error code
            print("Cannot create hard link across different drives.")
        raise

def copy_file(src: str, dest: str) -> None:
    if not src or not dest:
        raise Exception(f"Source and destination are required! Got {src} and {dest} respectively")
    
    shutil.copy(src, dest)

def get_all_dirs_in_dir(path: str) -> List[str]:
    path = Path(path)
    directories = [str(f) for f in path.iterdir() if f.is_dir()]
    return directories


def recursively_rm_dir(path: str) -> None:
    path = Path(path)
    if path.exists() and path.is_dir():
        shutil.rmtree(path)

def does_path_exist(path: str) -> bool:
    path = Path(path)
    return path.exists()

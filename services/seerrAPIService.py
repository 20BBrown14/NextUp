from schemas.seerr.models import User, MediaRequest
from typing import List
from constants.seerr import SEERR_SECRET_KEYS
import os
import requests
from typing import Optional, Dict, Any
from utils.fetch import make_request

def _make_authenticated_seerr_api_request(
    url: str,
    method: str = "GET",
    params: Optional[Dict[str, Any]] = None,
    body: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, Any]] = None,
    timeout: int = 30
) -> requests.Response:
    SEERR_API_KEY = os.environ.get(SEERR_SECRET_KEYS["SEERR_API_KEY"])
    SEERR_URL = os.environ.get(SEERR_SECRET_KEYS["SEERR_URL"])

    request_url = f"{SEERR_URL}/api/v1/{url}"
    headers = {
        **(headers or {}),
        "X-Api-Key": SEERR_API_KEY
    }
    return make_request(request_url, method, params, body, headers, timeout)


def get_seerr_users() -> List[User]:
    params = {
        "take": 100,
    }

    return _make_authenticated_seerr_api_request('user', params=params).json().get('results')

def make_media_request(tmdb_id: int, media_type: str, seerr_user_id: int, jellyfin_user_id: Optional[str] = None, seasons: List[int] = [1], auto_create_user: bool = False) -> MediaRequest:
    # Auto-resolve or validate the Seerr User ID
    if not seerr_user_id and jellyfin_user_id:
        seerr_user_id = get_or_create_seerr_user_by_jellyfin_id(
            jellyfin_user_id=jellyfin_user_id, 
            auto_create=auto_create_user
        )

    if not tmdb_id or not seerr_user_id:
        raise Exception(f"tvdb_id, seerr_user_id, and media_type are required to make requests. Got {tmdb_id}, {seerr_user_id}, and {media_type} respectively.")
    
    if media_type not in ['movie', 'tv']:
        raise Exception(f"media_type should be one of ['movie', tv']. Got {media_type}")
    
    body = {
        "mediaType": media_type,
        "mediaId": tmdb_id,
        "userId": seerr_user_id
    }

    if media_type == 'tv':
        body = {
            **body,
            "seasons": seasons
        }
    
    return _make_authenticated_seerr_api_request('request', method='POST', body=body).json()

def import_jellyfin_user(jellyfin_user_id: str) -> List[Dict[str, Any]]:
    """Imports a Jellyfin user into Jellyseerr using their Jellyfin User ID."""
    # Strip hyphens for compatibility across older and newer Jellyseerr versions
    clean_id = jellyfin_user_id.replace("-", "")
    body = {
        "jellyfinUserIds": [clean_id]
    }
    response = _make_authenticated_seerr_api_request("user/import-from-jellyfin", method="POST", body=body)
    return response.json()

def get_or_create_seerr_user_by_jellyfin_id(jellyfin_user_id: str, auto_create: bool = False) -> int:
    """Finds an existing Seerr user by Jellyfin ID. Auto-imports if missing and auto_create is True."""
    clean_id = jellyfin_user_id.replace("-", "")
    
    # Check if the user already exists in Jellyseerr
    users = get_seerr_users() or []
    for user in users:
        user_jellyfin_id = (user.get("jellyfinUserId") or "").replace("-", "")
        if user_jellyfin_id == clean_id:
            return user["id"]
            
    # User missing -> import only if config allows it
    if auto_create:
        imported_users = import_jellyfin_user(jellyfin_user_id)
        if imported_users and len(imported_users) > 0:
            return imported_users[0]["id"]
        raise Exception(f"Failed to auto-import Jellyfin user: {jellyfin_user_id}")
    
    raise Exception(f"Jellyfin user '{jellyfin_user_id}' not found in Jellyseerr and auto-creation is disabled.")
    
    


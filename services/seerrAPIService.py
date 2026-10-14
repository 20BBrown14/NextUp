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

def get_requests(
    requested_by: Optional[int] = None,
    media_type: str = 'all',
    filter: Optional[str] = None,
    page_size: int = 100,
) -> List[MediaRequest]:
    """
    Fetch Jellyseerr media requests, paging through all results.

    When `requested_by` (a Seerr user id) is provided, only that user's requests
    are returned. `media_type` is one of 'movie', 'tv', or 'all'. `filter` is an
    optional Seerr status filter (e.g. 'available').
    """
    if media_type not in ['movie', 'tv', 'all']:
        raise Exception(f"media_type must be one of ['movie', 'tv', 'all']. Got {media_type}")

    base_params: Dict[str, Any] = {
        "take": page_size,
        "mediaType": media_type,
    }
    if requested_by is not None:
        base_params["requestedBy"] = requested_by
    if filter is not None:
        base_params["filter"] = filter

    all_requests: List[MediaRequest] = []
    skip = 0
    while True:
        params = {**base_params, "skip": skip}
        response = _make_authenticated_seerr_api_request('request', params=params).json()

        results = response.get('results') or []
        all_requests.extend(results)

        page_info = response.get('pageInfo') or {}
        total_pages = page_info.get('pages')
        current_page = page_info.get('page')

        # Stop when we've consumed the last page or the server returned nothing.
        if not results:
            break
        if total_pages is not None and current_page is not None and current_page >= total_pages:
            break
        if total_pages is None and len(results) < page_size:
            break

        skip += page_size

    return all_requests


def get_user_by_jellyfin_id(jellyfin_user_id: str) -> Optional[User]:
    """
    Look up a Jellyseerr user by their Jellyfin user id.

    Returns None when no matching Seerr user exists (404). Hyphens are stripped
    for compatibility across Jellyseerr versions, mirroring the import helpers.
    """
    if not jellyfin_user_id:
        return None

    clean_id = jellyfin_user_id.replace("-", "")
    try:
        return _make_authenticated_seerr_api_request(f"user/jellyfin/{clean_id}").json()
    except requests.exceptions.HTTPError as e:
        if getattr(e.response, "status_code", None) == 404:
            return None
        raise

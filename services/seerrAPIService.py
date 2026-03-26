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

def make_media_request(tmdb_id: int, seerr_user_id: int, media_type: str, seasons: List[int] = [1]) -> MediaRequest:
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
    
    


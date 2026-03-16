import os
import requests
from utils.fetch import make_request
from typing import List, Optional, Dict, Any, Literal
from schemas.tmdb.models import TMDBRecommendation
from constants.tmdb import TMDB_SECRET_KEYS

def _make_authenticated_tmdb_api_request(
    url: str,
    method: str = "GET",
    params: Optional[Dict[str, Any]] = None,
    body: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, Any]] = None,
    timeout: int = 10
) -> requests.Response:
    TMDB_API_KEY = os.environ.get(TMDB_SECRET_KEYS["TMDB_API_KEY"])
    TMDB_URL = os.environ.get(TMDB_SECRET_KEYS["TMDB_URL"])

    request_url = f"{TMDB_URL}/{url}"
    headers = {
        **(headers or {}),
        "Authorization": f"Bearer {TMDB_API_KEY}"
    }
    return make_request(request_url, method, params, body, headers, timeout)

def get_recommendations_by_id(type: Literal['movie', 'tv'], id: str, pages: int = 3, sort_by: str = 'vote_average', sort_dir: str = 'desc', min_vote_count=10) -> List[TMDBRecommendation]:
    if not type or not type in ['movie', 'tv']:
        raise Exception(f"Type must be provided and be one of: [movie, tv]. Got {type}")
    
    if not id:
        raise Exception(f"{type.lower()} ID is required")
    
    unsorted_recommendations = []
    for i in range(pages):
        params = {
            "language": 'en-US',
            "page": i + 1
        }
        raw_recommendations = _make_authenticated_tmdb_api_request(f"{type.lower()}/{id}/recommendations", params=params).json().get("results")
        unsorted_recommendations.extend(raw_recommendations)

    sorted_recommendations = sorted(unsorted_recommendations, key=lambda x: x[sort_by], reverse=True if sort_dir == 'desc' else False)
    filtered_recos: List[TMDBRecommendation] = [reco for reco in sorted_recommendations if reco['vote_count'] >= min_vote_count]
    
    return filtered_recos
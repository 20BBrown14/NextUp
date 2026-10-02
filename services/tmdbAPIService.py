import os
import threading
import requests
from cachetools import TTLCache, LRUCache, cached
from cachetools.keys import hashkey
from utils.fetch import make_request
from typing import List, Optional, Dict, Any, Literal, cast
from schemas.tmdb.models import TMDBMovieRecommendation, TMDBSeriesRecommendation, Genre
from constants.tmdb import TMDB_SECRET_KEYS
from constants.config import CONFIG_KEYS
from utils import logger

logger = logger.get_logger(__name__)

# ---------------------------------------------------------------------------
# Cache stores
#
# _genre_cache        – TV/movie genre lists from TMDB. These are static
#                       reference data that never change. No expiry.
#
# _recommendations_cache – Per-item recommendations keyed on type, ID, and
#                          fetch params. Vote counts shift, but not rapidly.
#                          2-hour TTL.
#
# _trending_cache     – Popular/upcoming lists. These reflect what's trending
#                       right now, so a 12-hour TTL is appropriate.
# ---------------------------------------------------------------------------

_cache_lock = threading.Lock()

_genre_cache: LRUCache = LRUCache(maxsize=10)             # no expiry
_recommendations_cache: TTLCache = TTLCache(maxsize=1000, ttl=7200)   # 2 hours
_trending_cache: TTLCache = TTLCache(maxsize=50, ttl=43200)           # 12 hours


def _make_authenticated_tmdb_api_request(
    url: str,
    method: str = "GET",
    params: Optional[Dict[str, Any]] = None,
    body: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, Any]] = None,
    timeout: int = 30
) -> requests.Response:
    TMDB_API_KEY = os.environ.get(TMDB_SECRET_KEYS["TMDB_API_KEY"])
    TMDB_URL = os.environ.get(TMDB_SECRET_KEYS["TMDB_URL"], 'https://api.themoviedb.org/3')

    request_url = f"{TMDB_URL}/{url}"
    headers = {
        **(headers or {}),
        "Authorization": f"Bearer {TMDB_API_KEY}"
    }

    return make_request(request_url, method, params, body, headers, timeout)


# --- Genre lists (static reference data, no expiry) ------------------------

@cached(cache=_genre_cache, key=lambda: hashkey('tv_genres'), lock=_cache_lock)
def get_tv_genres() -> List[Genre]:
    genres = _make_authenticated_tmdb_api_request('genre/tv/list').json().get('genres')
    return [{'id': genre.get('id'), 'name': genre.get('name').lower()} for genre in genres]

@cached(cache=_genre_cache, key=lambda: hashkey('movie_genres'), lock=_cache_lock)
def get_movie_genres():
    genres = _make_authenticated_tmdb_api_request('genre/movie/list').json().get('genres')
    return [{'id': genre.get('id'), 'name': genre.get('name').lower()} for genre in genres]


# --- Per-item recommendations (2-hour TTL) ---------------------------------

@cached(
    cache=_recommendations_cache,
    key=lambda type, id, pages=3, sort_by='vote_average', sort_dir='desc', min_vote_count=10: hashkey(type, id, pages, sort_by, sort_dir, min_vote_count),
    lock=_cache_lock
)
def get_recommendations_by_id(type: Literal['movie', 'tv'], id: str, pages: int = 3, sort_by: str = 'vote_average', sort_dir: str = 'desc', min_vote_count=10) -> List[TMDBMovieRecommendation | TMDBSeriesRecommendation]:
    LANGUAGE = os.environ.get(CONFIG_KEYS["LANGUAGE"], 'en-US')
    ENFORCE_ORIG_LANGUAGE = os.environ.get(CONFIG_KEYS["ENFORCE_ORIG_LANGUAGE"], 'false').lower() == 'true'
    orig_language_code = LANGUAGE.split('-')[0]

    if not type or not type in ['movie', 'tv']:
        raise Exception(f"Type must be provided and be one of: [movie, tv]. Got {type}")
    
    if not id:
        raise Exception(f"{type.lower()} ID is required")
    
    unsorted_recommendations = []
    for i in range(pages):
        params = {
            "language": LANGUAGE,
            "page": i + 1
        }
        raw_recommendations = _make_authenticated_tmdb_api_request(f"{type.lower()}/{id}/recommendations", params=params).json().get("results")
        unsorted_recommendations.extend(raw_recommendations)

    sorted_recommendations = sorted(unsorted_recommendations, key=lambda x: x[sort_by], reverse=True if sort_dir == 'desc' else False)
    filtered_recos: List[TMDBMovieRecommendation | TMDBSeriesRecommendation] = [reco for reco in sorted_recommendations if reco['vote_count'] >= min_vote_count]

    if ENFORCE_ORIG_LANGUAGE:
        filtered_recos = [reco for reco in filtered_recos if reco.get('original_language') == orig_language_code]

    return filtered_recos


# --- Trending/popular lists (12-hour TTL) ----------------------------------
#
# Note: excluded_tmdb_ids is intentionally excluded from the cache key.
# The full list is cached; filtering against the caller's exclusion list
# is cheap and done in NextUp.py anyway.

@cached(cache=_trending_cache, key=lambda excluded_tmdb_ids=None: hashkey('popular_series'), lock=_cache_lock)
def get_popular_series(excluded_tmdb_ids: List[str] | None = None) -> List[TMDBSeriesRecommendation]:
    LANGUAGE = os.environ.get(CONFIG_KEYS["LANGUAGE"], 'en-US')
    ENFORCE_ORIG_LANGUAGE = os.environ.get(CONFIG_KEYS["ENFORCE_ORIG_LANGUAGE"], 'false').lower() == 'true'
    orig_language_code = LANGUAGE.split('-')[0]

    # PER_PAGE = 20 # Determined by counting api response
    current_page = 1
    POPULAR_SERIES_COUNT = int(os.environ.get(CONFIG_KEYS["POPULAR_SERIES_COUNT"], 100))
    filtered_recos = []
    while len(filtered_recos) < POPULAR_SERIES_COUNT:
        params = {
            "language": LANGUAGE,
            "page": current_page
        }
        recos_response = _make_authenticated_tmdb_api_request(f"tv/popular", params=params).json()
        recos = recos_response.get('results')
        if not recos:
            logger.error(f'Failed to fetch popular series due to TMDB API Failure: {recos_response}')
            logger.info(f'Continuing with popular series generation with only {len(filtered_recos)} recommendations.')
            break

        if not len(recos):
            logger.info(f'Cannot find anymore popular series. Stopping with {len(recos)} popular recommendations')
            break

        if ENFORCE_ORIG_LANGUAGE:
            recos = [reco for reco in recos if reco.get('original_language') == orig_language_code]

        if excluded_tmdb_ids and len(excluded_tmdb_ids):
            filtered_recos.extend([reco for reco in recos if reco.get('id') not in excluded_tmdb_ids])
        else:
            filtered_recos.extend(recos)

        current_page = current_page + 1
    
    return filtered_recos[:POPULAR_SERIES_COUNT]

@cached(cache=_trending_cache, key=lambda excluded_tmdb_ids=None: hashkey('popular_movies'), lock=_cache_lock)
def get_popular_movies(excluded_tmdb_ids: List[str] | None = None) -> List[TMDBMovieRecommendation]:
    LANGUAGE = os.environ.get(CONFIG_KEYS["LANGUAGE"], 'en-US')
    ENFORCE_ORIG_LANGUAGE = os.environ.get(CONFIG_KEYS["ENFORCE_ORIG_LANGUAGE"], 'false').lower() == 'true'
    orig_language_code = LANGUAGE.split('-')[0]

    # PER_PAGE = 20 # Determined by counting api response
    current_page = 1
    POPULAR_MOVIES_COUNT = int(os.environ.get(CONFIG_KEYS["POPULAR_MOVIES_COUNT"], 50))
    filtered_recos = []
    while len(filtered_recos) < POPULAR_MOVIES_COUNT:
        params = {
            "language": LANGUAGE,
            "page": current_page
        }
        recos_response = _make_authenticated_tmdb_api_request(f"movie/popular", params=params).json()
        recos = recos_response.get('results')
        if not recos:
            logger.error(f'Failed to fetch popular movies due to TMDB API Failure: {recos_response}')
            logger.info(f'Continuing with popular movies generation with only {len(filtered_recos)} recommendations.')
            break

        if not len(recos):
            logger.info(f'Cannot find anymore popular movies. Stopping with {len(recos)} popular recommendations')
            break

        if ENFORCE_ORIG_LANGUAGE:
            recos = [reco for reco in recos if reco.get('original_language') == orig_language_code]

        if excluded_tmdb_ids and len(excluded_tmdb_ids):
            filtered_recos.extend([reco for reco in recos if reco.get('id') not in excluded_tmdb_ids])
        else:
            filtered_recos.extend(recos)

        current_page = current_page + 1
    
    return filtered_recos[:POPULAR_MOVIES_COUNT]

@cached(cache=_trending_cache, key=lambda excluded_tmdb_ids=None: hashkey('upcoming_movies'), lock=_cache_lock)
def get_upcoming_movies(excluded_tmdb_ids: List[str] | None = None) -> List[TMDBMovieRecommendation]:
    LANGUAGE = os.environ.get(CONFIG_KEYS["LANGUAGE"], 'en-US')
    ENFORCE_ORIG_LANGUAGE = os.environ.get(CONFIG_KEYS["ENFORCE_ORIG_LANGUAGE"], 'false').lower() == 'true'
    orig_language_code = LANGUAGE.split('-')[0]

    # PER_PAGE = 20 # Determined by counting api response
    current_page = 1
    UPCOMING_MOVIES_COUNT = int(os.environ.get(CONFIG_KEYS["UPCOMING_MOVIES_COUNT"], 50))
    filtered_recos = []
    while len(filtered_recos) < UPCOMING_MOVIES_COUNT:
        params = {
            "language": LANGUAGE,
            "page": current_page
        }
        recos_response = _make_authenticated_tmdb_api_request(f"movie/upcoming", params=params).json()
        recos = recos_response.get('results')
        if not recos:
            logger.error(f'Failed to fetch upcoming movies due to TMDB API Failure: {recos_response}')
            logger.info(f'Continuing with upcoming movies generation with only {len(filtered_recos)} recommendations.')
            break
        if not len(recos):
            logger.info(f'Cannot find anymore upcoming movies. Stopping with {len(recos)} upcoming recommendations')
            break

        if ENFORCE_ORIG_LANGUAGE:
            recos = [reco for reco in recos if reco.get('original_language') == orig_language_code]

        if excluded_tmdb_ids and len(excluded_tmdb_ids):
            filtered_recos.extend([reco for reco in recos if reco.get('id') not in excluded_tmdb_ids])
        else:
            filtered_recos.extend(recos)

        current_page = current_page + 1
    
    return filtered_recos[:UPCOMING_MOVIES_COUNT]

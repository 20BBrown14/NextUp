import os
import time
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

_MAX_RETRIES = 5          # retry attempts after the initial request
_MAX_BACKOFF_SECONDS = 60  # upper bound for any single wait

# Proactive client-side cap. TMDB tolerates ~40 req/s; stay under that so a cold
# run resolving many external ids can't trip server-side rate limiting.
_MAX_REQUESTS_PER_SECOND = 30
_throttle_lock = threading.Lock()
_request_timestamps: List[float] = []


def _throttle() -> None:
    """Block until starting another request keeps us at or below
    _MAX_REQUESTS_PER_SECOND over the trailing one-second window."""
    while True:
        with _throttle_lock:
            now = time.monotonic()
            while _request_timestamps and now - _request_timestamps[0] >= 1.0:
                _request_timestamps.pop(0)

            if len(_request_timestamps) < _MAX_REQUESTS_PER_SECOND:
                _request_timestamps.append(now)
                return

            sleep_for = 1.0 - (now - _request_timestamps[0])

        if sleep_for > 0:
            time.sleep(sleep_for)


def _retry_after_seconds(response: Optional[requests.Response], attempt: int) -> float:
    if response is not None:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return min(float(retry_after), _MAX_BACKOFF_SECONDS)
            except (TypeError, ValueError):
                pass

    # Exponential backoff fallback: 1s, 2s, 4s, 8s, ... capped.
    return min(2 ** attempt, _MAX_BACKOFF_SECONDS)

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

# External-id -> TMDB-id mappings. An external id is a stable property of the
# title and effectively never changes, so no expiry; evicts oldest once full.
_external_id_cache: LRUCache = LRUCache(maxsize=10000)


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

    for attempt in range(_MAX_RETRIES + 1):
        try:
            _throttle()
            return make_request(request_url, method, params, body, headers, timeout)
        except requests.exceptions.HTTPError as e:
            response = e.response
            if response is None or response.status_code != 429:
                raise

            if attempt >= _MAX_RETRIES:
                logger.error(
                    f"TMDB rate limit (429) still in effect for {request_url} "
                    f"after {_MAX_RETRIES} retries. Giving up."
                )
                raise

            wait_seconds = _retry_after_seconds(response, attempt)
            logger.warning(
                f"TMDB rate limited (429) on {request_url}. "
                f"Waiting {wait_seconds:.0f}s before retry "
                f"{attempt + 1}/{_MAX_RETRIES}."
            )
            time.sleep(wait_seconds)

    # Unreachable: the loop either returns a response or raises.
    raise RuntimeError("TMDB request retry loop exited unexpectedly")


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

@cached(
    cache=_trending_cache,
    key=lambda endpoint, page: hashkey('trending_page', endpoint, page),
    lock=_cache_lock
)
def _fetch_trending_page(endpoint: str, page: int) -> List[Dict[str, Any]]:
    """Fetch and cache a single page of a trending endpoint
    ("tv/popular" | "movie/popular" | "movie/upcoming"). Returns [] on API
    failure or past the last page."""
    LANGUAGE = os.environ.get(CONFIG_KEYS["LANGUAGE"], 'en-US')

    recos_response = _make_authenticated_tmdb_api_request(
        endpoint, params={"language": LANGUAGE, "page": page}
    ).json()
    recos = recos_response.get('results')
    if not recos:
        logger.error(f'Failed to fetch {endpoint} page {page} from TMDB: {recos_response}')
        return []

    return recos


def _collect_trending(endpoint: str, count: int, excluded_tmdb_ids: List[int] | None) -> List[Dict[str, Any]]:
    """Page through `endpoint`, applying language and exclusion filters, until
    `count` items survive or the source runs out."""
    LANGUAGE = os.environ.get(CONFIG_KEYS["LANGUAGE"], 'en-US')
    ENFORCE_ORIG_LANGUAGE = os.environ.get(CONFIG_KEYS["ENFORCE_ORIG_LANGUAGE"], 'false').lower() == 'true'
    orig_language_code = LANGUAGE.split('-')[0]
    excluded = set(excluded_tmdb_ids) if excluded_tmdb_ids else set()

    collected: List[Dict[str, Any]] = []
    page = 1
    while len(collected) < count:
        recos = _fetch_trending_page(endpoint, page)
        if not recos:
            logger.info(f'No more results for {endpoint}. Stopping with {len(collected)} recommendations.')
            break

        if ENFORCE_ORIG_LANGUAGE:
            recos = [reco for reco in recos if reco.get('original_language') == orig_language_code]

        if excluded:
            recos = [reco for reco in recos if reco.get('id') not in excluded]

        collected.extend(recos)
        page += 1

    return collected[:count]


def get_popular_series(excluded_tmdb_ids: List[int] | None = None) -> List[TMDBSeriesRecommendation]:
    POPULAR_SERIES_COUNT = int(os.environ.get(CONFIG_KEYS["POPULAR_SERIES_COUNT"], 100))
    return cast(List[TMDBSeriesRecommendation], _collect_trending("tv/popular", POPULAR_SERIES_COUNT, excluded_tmdb_ids))


def get_popular_movies(excluded_tmdb_ids: List[int] | None = None) -> List[TMDBMovieRecommendation]:
    POPULAR_MOVIES_COUNT = int(os.environ.get(CONFIG_KEYS["POPULAR_MOVIES_COUNT"], 50))
    return cast(List[TMDBMovieRecommendation], _collect_trending("movie/popular", POPULAR_MOVIES_COUNT, excluded_tmdb_ids))


def get_upcoming_movies(excluded_tmdb_ids: List[int] | None = None) -> List[TMDBMovieRecommendation]:
    UPCOMING_MOVIES_COUNT = int(os.environ.get(CONFIG_KEYS["UPCOMING_MOVIES_COUNT"], 50))
    return cast(List[TMDBMovieRecommendation], _collect_trending("movie/upcoming", UPCOMING_MOVIES_COUNT, excluded_tmdb_ids))


# --- External id resolution (no expiry) ------------------------------------

# Jellyfin provider-id key -> TMDB external_source value.
_EXTERNAL_SOURCE_BY_PROVIDER = {
    "Imdb": "imdb_id",
    "Tvdb": "tvdb_id",
}

# TMDB media type -> the results key it lands in on the /find response.
_FIND_RESULTS_KEY = {
    "movie": "movie_results",
    "tv": "tv_results",
}


@cached(
    cache=_external_id_cache,
    key=lambda provider, external_id, media_type: hashkey('external_id', provider, external_id, media_type),
    lock=_cache_lock
)
def get_tmdb_id_from_external_id(provider: str, external_id: str, media_type: Literal['movie', 'tv']) -> Optional[int]:
    """Resolve a non-TMDB provider id (IMDb/TVDB) to a TMDB id via TMDB's /find
    endpoint. Returns None when the provider is unsupported or nothing matches."""
    external_source = _EXTERNAL_SOURCE_BY_PROVIDER.get(provider)
    results_key = _FIND_RESULTS_KEY.get(media_type)
    if not external_source or not results_key or not external_id:
        return None

    params = {"external_source": external_source}
    response = _make_authenticated_tmdb_api_request(f"find/{external_id}", params=params).json()
    results = response.get(results_key) or []
    if not results:
        return None

    found_id = results[0].get("id")
    return int(found_id) if found_id is not None else None

import requests
import os
import threading
from cachetools import TTLCache, cached
from cachetools.keys import hashkey
from constants.watchstate import WATCHSTATE_SECRET_KEYS
from utils.fetch import make_request
from utils.helpers import parse_jellyfin_date
from utils import logger
from schemas.watchstate.watchstate import WatchStateHistory
from typing import Optional, Dict, Any, List, cast, NamedTuple
from datetime import date, timedelta
from collections import Counter

logger = logger.get_logger(__name__)

class Series(NamedTuple):
        name: str
        id: str
        genres: List[str]
        tmdb_id: str

class Movie(NamedTuple):
        name: str
        id: str
        genres: List[str]
        tmdb_id: str

# ---------------------------------------------------------------------------
# Cache stores
#
# _token_cache – WatchState auth token. Tokens are short-lived session
#                credentials; a 10-minute TTL keeps the token fresh without
#                re-authenticating on every single API request.
# ---------------------------------------------------------------------------

_cache_lock = threading.Lock()
_token_cache: TTLCache = TTLCache(maxsize=1, ttl=600)  # 10 minutes

_token_lock = threading.RLock()

user_token = None

_HISTORY_VIEW_FIELDS = "id,title,type,guids,metadata"

def _fetch_all_paginated_data(
    url: str,
    method: str = "GET",
    params: Optional[Dict[str, Any]] = None,
    body: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, Any]] = None,
    timeout: int = 30,
    data_key: str = None,
):
    if not data_key:
        raise Exception('data_key is required to fetch all paginated data')

    def _extract_page(page: int):
        page_params = {
            **(params or {}),
            "page": page
        }
        response = _make_authenticated_watchstate_api_request(
            url, method, page_params, body, headers, timeout
        ).json()

        if not isinstance(response, dict) or data_key not in response:
            raise Exception(
                f"Failed to find key '{data_key}' in response for page {page}."
            )

        items = response.get(data_key)
        if not isinstance(items, list):
            raise Exception(
                f"Expected '{data_key}' to be a list in response for page {page}, "
                f"got {type(items).__name__}."
            )

        paging = response.get('paging')
        if not isinstance(paging, dict):
            # No usable paging metadata means there are no further pages.
            paging = {}
        return items, paging

    data, paging = _extract_page(1)

    while paging.get('next_page') is not None:
        page_items, paging = _extract_page(paging.get('next_page'))
        data.extend(page_items)

    return data



def _make_authenticated_watchstate_api_request(
    url: str,
    method: str = "GET",
    params: Optional[Dict[str, Any]] = None,
    body: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, Any]] = None,
    timeout: int = 30
) -> requests.Response:
    auth_user()

    if not url:
        raise Exception('URL is required to make a request to watchstate.')

    with _token_lock:
        if not user_token:
            raise Exception("`auth_user` must be called and succeed before making authenticated requests.")

    WATCHSTATE_URL = os.environ.get(WATCHSTATE_SECRET_KEYS["WATCHSTATE_URL"])

    request_url = f"{WATCHSTATE_URL}/v1/api/{url}"
    base_headers = headers or {}

    def _request():
        with _token_lock:
            token_used = user_token
        request_headers = {
            **base_headers,
            "Authorization": f"Token {token_used}"
        }
        try:
            response = make_request(request_url, method, params, body, request_headers, timeout)
        except requests.exceptions.HTTPError as err:
            err._ws_token_used = token_used
            raise
        return response, token_used

    try:
        response, _ = _request()
        return response
    except requests.exceptions.HTTPError as e:
        status = getattr(e.response, "status_code", None)
        if status != 401:
            raise
        token_used = getattr(e, "_ws_token_used", None)
        with _token_lock:
            if token_used is None or user_token == token_used:
                refresh_token()
        response, _ = _request()
        return response

def _login() -> str:
    """Exchange username/password for a fresh signed user token."""
    global user_token
    WATCHSTATE_USERNAME = os.environ.get(WATCHSTATE_SECRET_KEYS["WATCHSTATE_USERNAME"])
    WATCHSTATE_PASSWORD = os.environ.get(WATCHSTATE_SECRET_KEYS["WATCHSTATE_PASSWORD"])
    WATCHSTATE_URL = os.environ.get(WATCHSTATE_SECRET_KEYS["WATCHSTATE_URL"])
    auth_url = f"{WATCHSTATE_URL}/v1/api/system/auth/login"
    body = {
        "username": WATCHSTATE_USERNAME,
        "password": WATCHSTATE_PASSWORD
    }

    token = make_request(auth_url, 'POST', body=body, should_log=False).json()
    with _token_lock:
        user_token = token.get('token')
        return user_token


@cached(cache=_token_cache, key=lambda: hashkey('auth_token'), lock=_cache_lock)
def auth_user() -> None:
    _login()
    return


def refresh_token() -> str:
    global user_token
    WATCHSTATE_URL = os.environ.get(WATCHSTATE_SECRET_KEYS["WATCHSTATE_URL"])

    with _token_lock:
        current = user_token

    if not current:
        return _login()

    refresh_url = f"{WATCHSTATE_URL}/v1/api/system/auth/refresh"
    headers = {"Authorization": f"Token {current}"}
    try:
        response = make_request(refresh_url, 'POST', headers=headers, should_log=False).json()
        refreshed = response.get('token')
        if not refreshed:
            raise Exception("Refresh response did not include a token.")
        with _token_lock:
            user_token = refreshed
            return user_token
    except Exception:
        logger.warning("WatchState token refresh failed; falling back to re-login.", exc_info=True)
        return _login()

# Returns a list of Movies
def get_user_watched_movies(jellyfin_user_name: str, max_lookback_days: int = None) -> List[Movie]:
    WATCHSTATE_MAIN_USER_TO_JELLYFIN_MAP = os.environ.get(WATCHSTATE_SECRET_KEYS["WATCHSTATE_MAIN_USER_TO_JELLYFIN_MAP"])
    headers = {
        'X-User': jellyfin_user_name if jellyfin_user_name != WATCHSTATE_MAIN_USER_TO_JELLYFIN_MAP else 'main'
    }
    params = {
        "perpage": 100,
        "type": 'movie',
        "watched": 1,
        "view": _HISTORY_VIEW_FIELDS
    }
    raw_history = _fetch_all_paginated_data('history', params=params, headers=headers, data_key='history')
    history = cast(List[WatchStateHistory], raw_history)
    today = date.today()
    max_days_ago = (today - timedelta(days=max_lookback_days)) if max_lookback_days else None
    
    last_x_day_movie_list = []
    for movie in history:
        metadata = movie.get('metadata')

        jellyfin_metadata = metadata.get(f"jellyfin_{jellyfin_user_name}") if f"jellyfin_{jellyfin_user_name}" in metadata else metadata.get('jellyfin')
        if not jellyfin_metadata:
            continue

        last_played = jellyfin_metadata.get("played_at")
        if not last_played:
            continue
        last_played_date = None
        try:
             last_played_date = date.fromisoformat(parse_jellyfin_date(last_played))
        except (ValueError, AttributeError):
             last_played_date = date.fromtimestamp(int(last_played))

        if not max_lookback_days or last_played_date > max_days_ago:
            last_x_day_movie_list.append(movie)

    movies = []
    for movie in last_x_day_movie_list:
        metadata = movie.get('metadata')
        jellyfin_metadata = metadata.get(f"jellyfin_{jellyfin_user_name}") if f"jellyfin_{jellyfin_user_name}" in metadata else metadata.get('jellyfin')
        title = movie.get('title')
        jellyfin_id = jellyfin_metadata.get('id')
        guids = movie.get('guids')
        tmdb_id = guids.get('guid_tmdb') if isinstance(guids, dict) else None
        if not tmdb_id:
            continue
        raw_genres = jellyfin_metadata.get('extra', {}).get('genres', [])
        genres = [genre.lower() for genre in raw_genres]
        movies.append(Movie(title, jellyfin_id, genres, tmdb_id))

    return movies

# returns a list of Series
def get_user_watched_series(jellyfin_user_name: str, max_lookback_days: int = None, min_episode_watch_count: int = None) -> List[Series]:
    WATCHSTATE_MAIN_USER_TO_JELLYFIN_MAP = os.environ.get(WATCHSTATE_SECRET_KEYS["WATCHSTATE_MAIN_USER_TO_JELLYFIN_MAP"])
    headers = {
        'X-User': jellyfin_user_name if jellyfin_user_name != WATCHSTATE_MAIN_USER_TO_JELLYFIN_MAP else 'main'
    }
    params = {
        "perpage": 200,
        "watched": 1,
        "type": "episode",
        "view": _HISTORY_VIEW_FIELDS
    }


    raw_history = _fetch_all_paginated_data('history', params=params, headers=headers, data_key='history')
    history = cast(List[WatchStateHistory], raw_history)
    today = date.today()
    max_days_ago = (today - timedelta(days=max_lookback_days)) if max_lookback_days else None

    last_x_day_series_list = []
    for episode in history:
        metadata = episode.get('metadata')

        jellyfin_metadata = metadata.get(f"jellyfin_{jellyfin_user_name}") if f"jellyfin_{jellyfin_user_name}" in metadata else metadata.get('jellyfin')
        if not jellyfin_metadata:
            continue

        last_played = jellyfin_metadata.get("played_at")
        if not last_played:
            continue
        last_played_date = None
        try:
             last_played_date = date.fromisoformat(parse_jellyfin_date(last_played))
        except (ValueError, AttributeError):
             last_played_date = date.fromtimestamp(int(last_played))

        if not max_lookback_days or last_played_date > max_days_ago:
            series_title = jellyfin_metadata.get('title')
            series_id = jellyfin_metadata.get('show')

            parent = jellyfin_metadata.get('parent')
            series_tmdb = parent.get('guid_tmdb') if isinstance(parent, dict) else None

            if not series_tmdb:
                continue
            raw_series_genres = jellyfin_metadata.get('extra', {}).get('genres', [])
            series_genres = [genre.lower() for genre in raw_series_genres]
            new_series = Series(series_title, series_id, series_genres, series_tmdb)
            last_x_day_series_list.append(new_series)

    filtered_user_series_id_list = [series for series in last_x_day_series_list if series is not None]
    counts = Counter(series.id for series in filtered_user_series_id_list)

    id_to_series = {series.id: series for series in filtered_user_series_id_list}
    deduplicated_user_series_list = [
        id_to_series[s_id] 
        for s_id, count in counts.items() 
        if count >= min_episode_watch_count
    ]

    return deduplicated_user_series_list
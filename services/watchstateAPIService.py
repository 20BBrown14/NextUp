import requests
import os
from constants.watchstate import WATCHSTATE_SECRET_KEYS
from utils.fetch import make_request
from utils.helpers import parse_jellyfin_date
from schemas.watchstate.watchstate import WatchStateHistory
from typing import Optional, Dict, Any, List, cast, NamedTuple
from datetime import date, timedelta
from collections import Counter

class Series(NamedTuple):
        name: str
        id: str
        tmdb_id: str

class Movie(NamedTuple):
        name: str
        id: str
        tmdb_id: str

user_token = None

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
    
    params = {
        **params,
        "page": 1
    }
    
    response = _make_authenticated_watchstate_api_request(url, method, params, body, headers, timeout).json()

    if data_key not in response:
        raise Exception(f"Failed to find key ${data_key} in response.")
    
    paging = response.get('paging')
    data = response.get(data_key)

    while paging.get('next_page') is not None:
        params = {
            **params,
            "page": paging.get('next_page')
        }
        response = _make_authenticated_watchstate_api_request(url, method, params, body, headers, timeout).json()
        paging = response.get('paging')
        data.extend(response.get(data_key))

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
    
    if not user_token:
        raise Exception("`auth_user` must be called and succeed before making authenticated requests.")
    
    WATCHSTATE_URL = os.environ.get(WATCHSTATE_SECRET_KEYS["WATCHSTATE_URL"])

    request_url = f"{WATCHSTATE_URL}/v1/api/{url}"
    headers = {
        **(headers or {}),
        "Authorization": f"Token {user_token}"
    }
    return make_request(request_url, method, params, body, headers, timeout)

def auth_user() -> requests.Response:
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
    user_token = token.get('token')
    return

# Returns a list of Movies
def get_user_watched_movies(jellyfin_user_name: str, max_lookback_days: int = None) -> List[Movie]:
    WATCHSTATE_MAIN_USER_TO_JELLYFIN_MAP = os.environ.get(WATCHSTATE_SECRET_KEYS["WATCHSTATE_MAIN_USER_TO_JELLYFIN_MAP"])
    headers = {
        'X-User': jellyfin_user_name if jellyfin_user_name != WATCHSTATE_MAIN_USER_TO_JELLYFIN_MAP else 'main'
    }
    params = {
        "perpage": 100,
        "type": 'movie',
        "watched": 1
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
        except ValueError:
             last_played_date = date.fromtimestamp(int(last_played))

        if not max_lookback_days or last_played_date > max_days_ago:
            last_x_day_movie_list.append(movie)

    movies = []
    for movie in last_x_day_movie_list:
        metadata = movie.get('metadata')
        jellyfin_metadata = metadata.get(f"jellyfin_{jellyfin_user_name}") if f"jellyfin_{jellyfin_user_name}" in metadata else metadata.get('jellyfin')
        title = movie.get('title')
        jellyfin_id = jellyfin_metadata.get('id')
        tmdb_id = movie.get('guids').get('guid_tmdb')
        movies.append(Movie(title, jellyfin_id, tmdb_id))

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
        "type": "series"
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
            series_tmdb = jellyfin_metadata.get('parent').get('guid_tmdb')
            new_series = Series(series_title, series_id, series_tmdb)
            last_x_day_series_list.append(new_series)

    filtered_user_series_id_list = [series for series in last_x_day_series_list if series is not None]
    counts = Counter(series for series in filtered_user_series_id_list)

    deduplicated_user_series_list = [series for series, count in counts.items() if count >= min_episode_watch_count]

    return deduplicated_user_series_list
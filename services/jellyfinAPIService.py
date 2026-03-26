import requests
import os
from constants.jellyfin import JELLYFIN_SECRET_KEYS
from utils.fetch import make_request
from utils.helpers import parse_jellyfin_date, convert_string_to_uuid
from schemas.jellyfin.models import UserDto, BaseItemDto
from typing import Optional, Dict, Any, List, cast, NamedTuple
from datetime import date, timedelta, datetime
from constants.config import CONFIG_KEYS

class Series(NamedTuple):
        name: str
        id: str
        tmdb_id: str

class Movie(NamedTuple):
        name: str
        id: str
        tmdb_id: str

def _make_authenticated_jellyfin_api_request(
    url: str,
    method: str = "GET",
    params: Optional[Dict[str, Any]] = None,
    body: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, Any]] = None,
    timeout: int = 30
) -> requests.Response:
    JELLYFIN_API_KEY = os.environ.get(JELLYFIN_SECRET_KEYS["JELLYFIN_API_KEY"])
    JELLYFIN_URL = os.environ.get(JELLYFIN_SECRET_KEYS["JELLYFIN_URL"])

    request_url = f"{JELLYFIN_URL}/{url}"
    headers = {
        **(headers or {}),
        "Authorization": f"MediaBrowser Token=\"{JELLYFIN_API_KEY}\""
    }
    return make_request(request_url, method, params, body, headers, timeout)
    
def get_users() -> List[UserDto]:
    users = _make_authenticated_jellyfin_api_request('Users').json()
    return users

def get_configured_users() -> List[UserDto]:
    all_users = get_users()
    configured_users = os.environ.get(JELLYFIN_SECRET_KEYS["JELLYFIN_USERS"]).lower().split(',')
    return [user for user in all_users if user['Name'].lower() in configured_users]

# Guaranteed to return in the same order, None for missing values
def get_series_provider_ids_by_ids(series_ids: List[str]) -> List[BaseItemDto]:
    params = {
        "Fields": "ProviderIds",
        "ids": ','.join(series_ids)
    }

    raw_series_list = _make_authenticated_jellyfin_api_request(f"Items", params=params).json().get("Items", [])
    series_list = cast(List[BaseItemDto], raw_series_list)

    tmdb_list = [series.get("ProviderIds", {}).get("Tmdb", None) for series in series_list if series.get("ProviderIds", {}).get("Tmdb")]

    return tmdb_list

def get_user_watched_series_ids(user_id: str, max_days: int = None) -> List[Series]:    
    params = {
        "Filters": "IsPlayed",
        "Recursive": True,
        "IncludeItemTypes": "Episode"
    }
    raw_user_played_episode_list = _make_authenticated_jellyfin_api_request(f"Users/{user_id}/Items", params=params).json().get("Items", [])
    user_played_episode_list = cast(List[BaseItemDto], raw_user_played_episode_list)

    today = date.today()
    max_days_ago = (today - timedelta(days=max_days)) if max_days else None

    last_x_days_episode_list = []
    for episode in user_played_episode_list:
        user_data = episode.get("UserData")
        if not episode.get("UserData"):
            continue

        last_played_date = user_data.get("LastPlayedDate")
        if not last_played_date:
            continue

        if not max_days_ago or date.fromisoformat(parse_jellyfin_date(last_played_date)) > max_days_ago:
            last_x_days_episode_list.append(episode)


    user_series_id_list = [(episode.get("SeriesName"), episode.get("SeriesId")) for episode in last_x_days_episode_list]
    deduplicated_user_series_list = list(set([id for id in user_series_id_list if id is not None]))

    series_ids: list[str] = [series[1] for series in deduplicated_user_series_list]
    tmdb_id_list = get_series_provider_ids_by_ids(series_ids)

    return [Series(*series, tmdb_id_list[index]) for index, series in enumerate(deduplicated_user_series_list) if tmdb_id_list[index] is not None]


def get_user_fully_watched_movies(user_id: str) -> List[BaseItemDto]:
    params = {
        "Filters": "IsPlayed",
        "Recursive": True,
        "IncludeItemTypes": "Movie",
        "Fields": "ProviderIds"
    }

    raw_user_played_movie_list = _make_authenticated_jellyfin_api_request(f"Users/{user_id}/Items", params=params).json().get("Items", [])
    user_played_movie_list = cast(List[BaseItemDto], raw_user_played_movie_list)
    return user_played_movie_list

def get_user_in_progress_movies(user_id: str, min_progress_percent: int = None) -> List[BaseItemDto]:
    params = {
        "Filters": "IsResumable",
        "Recursive": True,
        "IncludeItemTypes": "Movie",
        "Fields": "ProviderIds"
    }

    raw_user_in_progress_movie_list = _make_authenticated_jellyfin_api_request(f"Users/{user_id}/Items", params=params).json().get("Items", [])
    user_played_in_progress_list = cast(List[BaseItemDto], raw_user_in_progress_movie_list)
    if not min_progress_percent:
        return user_played_in_progress_list
    
    filtered_movie_list = []
    for movie in user_played_in_progress_list:
        if not movie:
            continue
        
        movie_user_data = movie.get("UserData")
        if not movie_user_data:
            continue

        played_percent = movie_user_data.get("PlayedPercentage")
        if played_percent < min_progress_percent:
            continue

        filtered_movie_list.append(movie)

    return filtered_movie_list

def get_all_user_movies(user_id: str, max_days: int = None, min_progress_percent: int = None) -> List[Movie]:
    all_movies = [*get_user_fully_watched_movies(user_id), *get_user_in_progress_movies(user_id, min_progress_percent)]

    today = date.today()
    max_days_ago = (today - timedelta(days=max_days)) if max_days else None

    last_x_day_movie_list = []
    for movie in all_movies:
        user_data = movie.get("UserData")
        if not movie.get("UserData"):
            continue

        last_played_date = user_data.get("LastPlayedDate")
        if not last_played_date:
            continue

        if not max_days_ago or date.fromisoformat(parse_jellyfin_date(last_played_date)) > max_days_ago:
            last_x_day_movie_list.append(movie)


    user_movie_id_list = [(movie.get("Name"), movie.get("Id"), movie.get("ProviderIds", {}).get("Tmdb")) for movie in last_x_day_movie_list]
    deduplicated_user_movie_list = list(set([id for id in user_movie_id_list if id is not None]))

    return [Movie(*movie) for movie in deduplicated_user_movie_list]

def get_all_available_movies(user_id: str = None) -> List[str]:
    RAW_MOVIE_LIBRARY_IDS = os.environ.get(CONFIG_KEYS["MOVIE_LIBRARY_IDS"])
    MOVIE_LIBRARY_IDS = RAW_MOVIE_LIBRARY_IDS.rsplit(',') if RAW_MOVIE_LIBRARY_IDS else []

    params = {
        "Recursive": True,
        "IncludeItemTypes": "Movie",
        "Fields": "ProviderIds,ParentId"
    }

    url = ''
    if user_id == None:
        url = 'Items'
    else:
        url = f"Users/{user_id}/Items"

    raw_movie_list = []
    if len(MOVIE_LIBRARY_IDS):
        for id in MOVIE_LIBRARY_IDS:
            extended_params = {**params, "ParentId": id}
            response = _make_authenticated_jellyfin_api_request(url, params=extended_params).json().get("Items", [])
            raw_movie_list.extend(response)
    else:
        response = _make_authenticated_jellyfin_api_request(url, params=params).json().get("Items", [])
        raw_movie_list.extend(response) 
    
    movie_list = cast(List[BaseItemDto], raw_movie_list)
    movie_tmdb_id_list = [movie.get("ProviderIds", {}).get("Tmdb") for movie in movie_list]
    return [int(id) for id in movie_tmdb_id_list if id is not None]

def get_all_available_series(user_id: str = None) -> List[str]:
    RAW_SERIES_LIBRARY_IDS = os.environ.get(CONFIG_KEYS["SERIES_LIBRARY_IDS"])
    SERIES_LIBRARY_IDS = RAW_SERIES_LIBRARY_IDS.rsplit(',') if RAW_SERIES_LIBRARY_IDS else []

    params = {
        "Recursive": True,
        "IncludeItemTypes": "Series",
        "Fields": "ProviderIds"
    }

    url = ''
    if user_id == None:
        url = 'Items'
    else:
        url = f"Users/{user_id}/Items"

    raw_series_list = []
    if len(SERIES_LIBRARY_IDS):
        for id in SERIES_LIBRARY_IDS:
            extended_params = {**params, "ParentId": id}
            response = _make_authenticated_jellyfin_api_request(url, params=extended_params).json().get("Items", [])
            raw_series_list.extend(response)
    else:
        response = _make_authenticated_jellyfin_api_request(url, params=params).json().get("Items", [])
        raw_series_list.extend(response) 

    
    series_list = cast(List[BaseItemDto], raw_series_list)
    series_tmdb_id_list = [movie.get("ProviderIds", {}).get("Tmdb") for movie in series_list]
    return [int(id) for id in series_tmdb_id_list if id is not None]

def delete_item_by_id(item_id: str):
    if not item_id:
        return
    
    return _make_authenticated_jellyfin_api_request(f"Items/{convert_string_to_uuid(item_id)}", method='DELETE')




import requests
import os
from constants.jellyfin import JELLYFIN_SECRET_KEYS
from utils.fetch import make_request
from utils.helpers import parse_jellyfin_date
from schemas.jellyfin.models import UserDto, BaseItemDto
from typing import Optional, Dict, Any, List, cast, NamedTuple
from datetime import date, timedelta, datetime

def _make_authenticated_jellyfin_api_request(
    url: str,
    method: str = "GET",
    params: Optional[Dict[str, Any]] = None,
    body: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, Any]] = None,
    timeout: int = 10
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
    return _make_authenticated_jellyfin_api_request('Users').get("Items", []).json()

def get_configured_users() -> List[UserDto]:
    all_users = get_users()
    configured_users = os.environ.get(JELLYFIN_SECRET_KEYS["JELLYFIN_USERS"]).lower().split(',')
    return [user for user in all_users if user['Name'].lower() in configured_users]

def get_user_watched_series_ids(user_id: str, max_days: int = None) -> List[BaseItemDto]:
    class Series(NamedTuple):
        name: str
        id: str
    
    params = {
        "Filters": "IsPlayed",
        "Recursive": True,
        "IncludeItemTypes": "Episode"
    }
    raw_user_played_episode_list = _make_authenticated_jellyfin_api_request(f"Users/{user_id}/Items", params=params).json().get("Items", [])
    user_played_episode_list = cast(List[BaseItemDto], raw_user_played_episode_list)
    print(user_played_episode_list[0])
    today = date.today()
    max_days_ago = (today - timedelta(days=max_days)) if max_days else None

    last_90_day_episode_list = []
    for episode in user_played_episode_list:
        user_data = episode.get("UserData")
        if not episode.get("UserData"):
            continue

        last_played_date = user_data.get("LastPlayedDate")
        if not last_played_date:
            continue

        if not max_days_ago or date.fromisoformat(parse_jellyfin_date(last_played_date)) > max_days_ago:
            last_90_day_episode_list.append(episode)


    user_series_id_list = [(episode.get("SeriesName"), episode.get("SeriesId")) for episode in last_90_day_episode_list]
    deduplicated_user_series_list = list(set([id for id in user_series_id_list if id is not None]))

    return [Series(*series) for series in deduplicated_user_series_list]


# def get_user_watched_movies(user_id: str) -> List[BaseItemDto]:
#     return _make_authenticated_jellyfin_api_request(f"Users/{user_id}/Items?Filters=IsPlayed&Resurvie=true&IncludeItemTypes=Movie").json()



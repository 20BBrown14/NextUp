import requests
import os
import threading
from cachetools import TTLCache, LRUCache, cached
from cachetools.keys import hashkey
from constants.jellyfin import JELLYFIN_SECRET_KEYS
from utils.fetch import make_request
from utils.helpers import parse_jellyfin_date, convert_string_to_uuid
from schemas.jellyfin.models import UserDto, BaseItemDto
from typing import Optional, Dict, Any, List, cast, NamedTuple
from datetime import date, timedelta
from constants.config import CONFIG_KEYS
from collections import Counter

class Series(NamedTuple):
        name: str
        id: str
        genres: List[str]
        tmdb_id: str # This should be last


class Movie(NamedTuple):
        name: str
        id: str
        genres: List[str]
        tmdb_id: str # This should be last


# ---------------------------------------------------------------------------
# Cache stores
#
# _library_cache  – available movies/series on the server. These only change
#                   when media is added or removed.
#
# _item_meta_cache – per-item TMDB IDs and genre lists keyed on a frozenset
#                    of Jellyfin item IDs. Metadata on existing library items
#                    never changes, so this cache has no expiry and only evicts
#                    when it reaches its size cap.
#
# _user_cache      – the Jellyfin user list. Users are rarely added/removed;
#                    a 30-minute TTL avoids unnecessary chatter.
#
# A single lock is shared across all caches because cachetools caches are not
# thread-safe by default and APScheduler runs jobs on background threads.
# ---------------------------------------------------------------------------

_cache_lock = threading.Lock()

_library_cache: TTLCache = TTLCache(maxsize=50, ttl=7200)    # 2 hours
_item_meta_cache: LRUCache = LRUCache(maxsize=1000)           # no expiry, evicts oldest when full
_user_cache: TTLCache = TTLCache(maxsize=5, ttl=1800)         # 30 minutes


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


# --- User list (stable, 30-minute TTL) -------------------------------------

@cached(cache=_user_cache, key=lambda: hashkey('users'), lock=_cache_lock)
def get_users() -> List[UserDto]:
    users = _make_authenticated_jellyfin_api_request('Users').json()
    return users

def get_configured_users() -> List[UserDto]:
    all_users = get_users()
    configured_users = os.environ.get(JELLYFIN_SECRET_KEYS["JELLYFIN_USERS"]).lower().split(',')
    return [user for user in all_users if user['Name'].lower() in configured_users]


# Guaranteed to return in the same order, None for missing values
@cached(
    cache=_item_meta_cache,
    key=lambda series_ids: hashkey('series_provider_ids', frozenset(series_ids)),
    lock=_cache_lock
)
def get_series_provider_ids_by_ids(series_ids: List[str]) -> List[List[str]]:
    params = {
        "Fields": "ProviderIds",
        "ids": ','.join(series_ids)
    }

    raw_series_list = _make_authenticated_jellyfin_api_request(f"Items", params=params).json().get("Items", [])
    series_list = cast(List[BaseItemDto], raw_series_list)

    tmdb_list = [series.get("ProviderIds", {}).get("Tmdb", None) for series in series_list if series.get("ProviderIds", {}).get("Tmdb")]

    return tmdb_list

# Guaranteed to return in the same order, None for missing values
@cached(
    cache=_item_meta_cache,
    key=lambda movie_ids: hashkey('movie_provider_ids', frozenset(movie_ids)),
    lock=_cache_lock
)
def get_movies_provider_ids_by_ids(movie_ids: List[str]) -> List[List[str]]:
    params = {
        "Fields": "ProviderIds",
        "ids": ','.join(movie_ids)
    }

    raw_movies_list = _make_authenticated_jellyfin_api_request(f"Items", params=params).json().get("Items", [])
    movies_list = cast(List[BaseItemDto], raw_movies_list)

    tmdb_list = [movie.get("ProviderIds", {}).get("Tmdb", None) for movie in movies_list if movie.get("ProviderIds", {}).get("Tmdb")]

    return tmdb_list

@cached(
    cache=_item_meta_cache,
    key=lambda series_ids: hashkey('series_genres', frozenset(series_ids)),
    lock=_cache_lock
)
def get_series_genres_by_ids(series_ids: List[str]) -> List[List[str]]:
    params = {
        "Fields": "Genres",
        "ids": ','.join(series_ids)
    }

    raw_series_list = _make_authenticated_jellyfin_api_request(f"Items", params=params).json().get("Items", [])
    series_list = cast(List[BaseItemDto], raw_series_list)

    raw_genre_list = [series.get("Genres", []) for series in series_list]
    genre_list = [[genre.lower() for genre in genres] for genres in raw_genre_list]

    return genre_list

@cached(
    cache=_item_meta_cache,
    key=lambda movie_ids: hashkey('movie_genres', frozenset(movie_ids)),
    lock=_cache_lock
)
def get_movie_genres_by_ids(movie_ids: List[str]) -> List[List[str]]:
    params = {
        "Fields": "Genres",
        "ids": ','.join(movie_ids)
    }

    raw_movies_list = _make_authenticated_jellyfin_api_request(f"Items", params=params).json().get("Items", [])
    movies_list = cast(List[BaseItemDto], raw_movies_list)

    raw_genre_list = [movies.get("Genres", []) for movies in movies_list]
    genre_list = [[genre.lower() for genre in genres] for genres in raw_genre_list]

    return genre_list


# --- Watch history (volatile – not cached) ----------------------------------

def get_user_watched_series_ids(user_id: str, max_days: int = None, min_episode_watch_count: int = None) -> List[Series]:    
    params = {
        "Filters": "IsPlayed",
        "Recursive": True,
        "IncludeItemTypes": "Episode",
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


    user_series_list = [(episode.get("SeriesName"), episode.get("SeriesId")) for episode in last_x_days_episode_list]
    filtered_user_series_id_list = [series for series in user_series_list if series is not None]
    counts = Counter(series for series in filtered_user_series_id_list)

    deduplicated_user_series_list = [series for series, count in counts.items() if count >= min_episode_watch_count]
    series_ids: list[str] = [series[1] for series in deduplicated_user_series_list]
    tmdb_id_list = get_series_provider_ids_by_ids(series_ids)
    genre_list = get_series_genres_by_ids(series_ids)
    return [Series(*series, genre_list[index] or [], tmdb_id_list[index]) for index, series in enumerate(deduplicated_user_series_list) if tmdb_id_list[index] is not None]


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


    user_movie_list = [(movie.get("Name"), movie.get("Id")) for movie in last_x_day_movie_list]
    
    filtered_user_movie_list = [movie for movie in user_movie_list if movie is not None]
    
    movie_ids: list[str] = [movie[1] for movie in filtered_user_movie_list]
    tmdb_id_list = get_movies_provider_ids_by_ids(movie_ids)
    genre_list = get_movie_genres_by_ids(movie_ids)
    return [Movie(*movie, genre_list[index] or [], tmdb_id_list[index]) for index, movie in enumerate(filtered_user_movie_list) if tmdb_id_list[index] is not None]


# --- Library availability (stable, 2-hour TTL) ------------------------------

@cached(
    cache=_library_cache,
    key=lambda user_id=None: hashkey('available_movies', user_id),
    lock=_cache_lock
)
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

@cached(
    cache=_library_cache,
    key=lambda user_id=None: hashkey('available_series', user_id),
    lock=_cache_lock
)
def get_all_available_series(user_id: str = None) -> List[int]:
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


# ===========================================================================
# Library + item resolution helpers
#
# None of these are cached: library and user-policy state must always be read
# fresh.
# ===========================================================================

DEFAULT_LIBRARY_OPTIONS: Dict[str, Any] = {
    "EnableRealtimeMonitor": True,
    "EnableChapterImageExtraction": False,
    "ExtractChapterImagesDuringLibraryScan": False,
    "EnableTrickplayImageExtraction": False,
    "ExtractTrickplayImagesDuringLibraryScan": False,
    "SaveTrickplayWithMedia": False,
    "SubtitleDownloadLanguages": [],
}


def get_item_path(item: BaseItemDto) -> Optional[str]:
    """Return the on-disk path for an item, preferring its first media source."""
    if not item:
        return None

    media_sources = item.get("MediaSources") or []
    for source in media_sources:
        source_path = source.get("Path")
        if source_path:
            return source_path

    return item.get("Path")


def get_items_by_tmdb_ids(tmdb_ids: List[int], item_type: str) -> List[BaseItemDto]:
    """Return server items of `item_type` ("Movie" or "Series") whose TMDB id is
    in `tmdb_ids`. Jellyfin can't filter by TMDB id, so filtering is client-side."""
    if item_type not in ["Movie", "Series"]:
        raise Exception(f"item_type must be one of ['Movie', 'Series']. Got {item_type}")

    if not tmdb_ids:
        return []

    wanted = {str(tmdb_id) for tmdb_id in tmdb_ids}

    params = {
        "Recursive": True,
        "IncludeItemTypes": item_type,
        "Fields": "ProviderIds,Path,MediaSources,ProductionYear"
    }

    raw_items = _make_authenticated_jellyfin_api_request("Items", params=params).json().get("Items", [])
    items = cast(List[BaseItemDto], raw_items)

    return [
        item for item in items
        if item.get("ProviderIds", {}).get("Tmdb") in wanted
    ]


def get_series_episode_paths(series_item_id: str) -> List[Dict[str, Any]]:
    """Return every episode of a series present on the server as
    {season, episode, path, name}. Episodes without a resolvable path are skipped."""
    if not series_item_id:
        return []

    params = {
        "Fields": "Path,MediaSources"
    }

    raw_episodes = _make_authenticated_jellyfin_api_request(
        f"Shows/{series_item_id}/Episodes", params=params
    ).json().get("Items", [])
    episodes = cast(List[BaseItemDto], raw_episodes)

    results: List[Dict[str, Any]] = []
    for episode in episodes:
        path = get_item_path(episode)
        if not path:
            continue
        results.append({
            "season": episode.get("ParentIndexNumber"),
            "episode": episode.get("IndexNumber"),
            "path": path,
            "name": episode.get("Name"),
        })

    return results


def get_virtual_folders() -> List[Dict[str, Any]]:
    """Return all Jellyfin libraries (virtual folders), including their ItemId."""
    return _make_authenticated_jellyfin_api_request("Library/VirtualFolders").json()


def get_virtual_folder_by_name(name: str) -> Optional[Dict[str, Any]]:
    """Return the virtual folder with the exact given Name, or None."""
    for folder in get_virtual_folders():
        if folder.get("Name") == name:
            return folder
    return None


def create_library(
    name: str,
    path: str,
    collection_type: str = "mixed",
    library_options: Dict[str, Any] = None,
    refresh: bool = True,
) -> None:
    """Create a Jellyfin library (virtual folder). Idempotency is the caller's
    responsibility."""
    params = {
        "name": name,
        "collectionType": collection_type,
        "paths": [path],
        "refreshLibrary": refresh,
    }
    body = {"LibraryOptions": library_options or DEFAULT_LIBRARY_OPTIONS}
    _make_authenticated_jellyfin_api_request(
        "Library/VirtualFolders", method="POST", params=params, body=body
    )


def refresh_libraries() -> None:
    """Trigger a Jellyfin library scan."""
    _make_authenticated_jellyfin_api_request("Library/Refresh", method="POST")


def get_user_policy(user_id: str) -> Dict[str, Any]:
    """Return a user's current policy object."""
    user = _make_authenticated_jellyfin_api_request(f"Users/{user_id}").json()
    return user.get("Policy") or {}


def add_library_to_user(user_id: str, library_item_id: str) -> None:
    """Grant a single user access to a library by its virtual-folder ItemId,
    appending to their EnabledFolders."""
    if not user_id or not library_item_id:
        raise Exception(
            f"user_id and library_item_id are required. "
            f"Got {user_id} and {library_item_id} respectively."
        )

    policy = get_user_policy(user_id)

    # Leave EnableAllFolders users untouched; downgrading them to an explicit
    # allow-list would silently shrink their access.
    if policy.get("EnableAllFolders"):
        return

    enabled_folders = list(policy.get("EnabledFolders") or [])
    if library_item_id in enabled_folders:
        return

    enabled_folders.append(library_item_id)
    policy["EnabledFolders"] = enabled_folders

    _make_authenticated_jellyfin_api_request(
        f"Users/{user_id}/Policy", method="POST", body=policy
    )


# ===========================================================================
# Collections (BoxSets)
#
# Used to build per-user "Requests - {user}" collections. Not cached: a
# collection's membership changes as users request media or media leaves the
# server, and reads drive a delta sync.
# ===========================================================================

def get_collections() -> List[BaseItemDto]:
    """Return every collection (BoxSet) on the server."""
    params = {
        "Recursive": True,
        "IncludeItemTypes": "BoxSet",
        "Fields": "ProviderIds",
    }
    raw_items = _make_authenticated_jellyfin_api_request("Items", params=params).json().get("Items", [])
    return cast(List[BaseItemDto], raw_items)


def get_collection_by_name(name: str) -> Optional[BaseItemDto]:
    """Return the collection with the exact given Name, or None."""
    for collection in get_collections():
        if collection.get("Name") == name:
            return collection
    return None


def get_collection_items(collection_id: str) -> List[BaseItemDto]:
    """Return the member items of a collection."""
    if not collection_id:
        return []

    params = {
        "ParentId": collection_id,
        "Fields": "ProviderIds",
    }
    raw_items = _make_authenticated_jellyfin_api_request("Items", params=params).json().get("Items", [])
    return cast(List[BaseItemDto], raw_items)


# Item ids are sent as a comma-delimited query param; a user with many requests
# can produce a URL that exceeds server/proxy length limits, so ids are chunked.
COLLECTION_ITEMS_BATCH_SIZE = 20


def _chunk(items: List[str], size: int):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def create_collection(name: str, item_ids: List[str] = None) -> str:
    """Create a collection, optionally seeding it with item ids. Returns the new
    collection's Id. Seeding is chunked: the first batch seeds the collection and
    any remainder is added afterwards."""
    item_ids = item_ids or []
    first_batch = item_ids[:COLLECTION_ITEMS_BATCH_SIZE]

    params: Dict[str, Any] = {"name": name}
    if first_batch:
        params["ids"] = ",".join(first_batch)

    response = _make_authenticated_jellyfin_api_request("Collections", method="POST", params=params).json()
    collection_id = response.get("Id")

    add_items_to_collection(collection_id, item_ids[COLLECTION_ITEMS_BATCH_SIZE:])

    return collection_id


def add_items_to_collection(collection_id: str, item_ids: List[str]) -> None:
    """Add items to a collection, chunked to keep each request's URL bounded.
    No-op on an empty list."""
    if not collection_id or not item_ids:
        return

    for batch in _chunk(item_ids, COLLECTION_ITEMS_BATCH_SIZE):
        _make_authenticated_jellyfin_api_request(
            f"Collections/{collection_id}/Items", method="POST", params={"ids": ",".join(batch)}
        )


def remove_items_from_collection(collection_id: str, item_ids: List[str]) -> None:
    """Remove items from a collection, chunked to keep each request's URL bounded.
    No-op on an empty list."""
    if not collection_id or not item_ids:
        return

    for batch in _chunk(item_ids, COLLECTION_ITEMS_BATCH_SIZE):
        _make_authenticated_jellyfin_api_request(
            f"Collections/{collection_id}/Items", method="DELETE", params={"ids": ",".join(batch)}
        )

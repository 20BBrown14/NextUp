from typing import List

class WatchStateTokenResponse:
    token: str

class WatchStateGUIDs:
    guid_imdb: str
    guid_tmdb: str | None
    guid_tvdb: str | None

class WatchStateHistoryParent:
    guid_imdb: str
    guid_tmdb: str
    guid_tvdb: str
    guid_tvrage: str

class WatchStateHistoryMetadataExtra:
    genres: List[str]
    date: str
    favorite: int
    overview: str

class WatchStateHistoryMetadata:
    id: str
    type: str
    watched: str
    via: str
    title: str
    guids: WatchStateGUIDs
    added_at: str
    extra: WatchStateHistoryMetadataExtra
    library: str
    year: str
    multi: bool
    path: str
    progress: str
    played_at: str
    webUrl: str

class WatchStateHistoryJellyfinMetadata:
    jellyfin: WatchStateHistoryMetadata

class WatchStateHistory:
    id: int
    type: str
    updated: int
    watched: int
    via: str
    title: str
    year: int
    season: int | None
    episode: int | None
    parent: WatchStateHistoryParent
    guids: WatchStateGUIDs
    metadata: WatchStateHistoryJellyfinMetadata
    created_at: int
    updated_at: int
    progress: None # TD
    event: str
    content_title: str | None
    content_path: str
    content_overview: str
    content_genres: List[str]
    rguids: List #TD
    reported_by: List[str]
    webUrl: str
    not_reported_by: List
    isTained: bool
    duplicate_reference_ids: List

class WatchStatePaging:
    total: int
    perpage: int
    current_page: int
    first_page: int
    next_page: int | None
    prev_page: int | None
    last_page: int

class WatchStateFilters:
    watched: str
    type: str

class WatchStatePagingLinks:
    self: str
    first_url: str
    next_url: str | None
    prev_url: str | None
    last_url: str

class WatchStateHistoryResponse:
    paging: WatchStatePaging
    filters: WatchStateFilters
    history: List[WatchStateHistory]
    links: WatchStatePagingLinks
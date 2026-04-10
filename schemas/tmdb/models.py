from typing import TypedDict, List
from typing_extensions import TypedDict

class TMDBMovieRecommendation(TypedDict, closed=True):
    adult: bool
    backdrop_path: str
    id: int
    title: str
    original_title: str
    overview: str
    poster_path: str
    media_type: str
    original_language: str
    genre_ids: List[int]
    popularity: float
    release_date: str
    video: bool
    vote_average: float
    vote_count: int

class TMDBSeriesRecommendation(TypedDict, closed=True):
    adult: bool
    backdrop_path: str
    id: int
    name: str
    original_name: str
    overview: str
    poster_path: str
    media_type: str
    original_language: str
    genre_ids: List[int]
    popularity: float
    first_air_date: str
    vote_average: float
    vote_count: int
    origin_country: List[str]

class TMDBPopularMoviesResponse(TypedDict, closed=True):
    page: int
    results: List[TMDBMovieRecommendation]
    total_pages: int
    total_result: int

class TMDBPopularSeriesResponse(TypedDict, closed=True):
    page: int
    results: List[TMDBSeriesRecommendation]
    total_pages: int
    total_result: int

class Genre(TypedDict, closed=True):
    id: int
    name: str
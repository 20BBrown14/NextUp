from typing import TypedDict, List
from typing_extensions import TypedDict

class TMDBRecommendation(TypedDict, closed=True):
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
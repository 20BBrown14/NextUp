from dataclasses import dataclass
from typing import List, Optional, TypedDict

class JellyfinMetadata:
    mediaType: int
    releaseDate: str
    genreIds: List[int]
    originalLanguage: str
    originalTitle: str
    voteAverage: float
    voteCount: int
    backdropPath: str
    posterPath: str
    createdDate: str
    networkTag: str
    networkId: int
    title: str
    adult: bool
    video: bool
    id: int
    popularity: float
    overview: str
    
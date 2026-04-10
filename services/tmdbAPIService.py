import os
import requests
from utils.fetch import make_request
from typing import List, Optional, Dict, Any, Literal, cast
from schemas.tmdb.models import TMDBMovieRecommendation, TMDBSeriesRecommendation, Genre
from constants.tmdb import TMDB_SECRET_KEYS
from constants.config import CONFIG_KEYS
from utils import logger

logger = logger.get_logger(__name__)

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
    return make_request(request_url, method, params, body, headers, timeout)

def get_tv_genres() -> List[Genre]:
    return _make_authenticated_tmdb_api_request('genre/tv/list').json().get('genres')

def get_movie_genres():
    return _make_authenticated_tmdb_api_request('genre/movie/list').json().get('genres')

def get_recommendations_by_id(type: Literal['movie', 'tv'], id: str, pages: int = 3, sort_by: str = 'vote_average', sort_dir: str = 'desc', min_vote_count=10) -> List[TMDBMovieRecommendation | TMDBSeriesRecommendation]:
    if not type or not type in ['movie', 'tv']:
        raise Exception(f"Type must be provided and be one of: [movie, tv]. Got {type}")
    
    if not id:
        raise Exception(f"{type.lower()} ID is required")
    
    unsorted_recommendations = []
    for i in range(pages):
        params = {
            "language": 'en-US',
            "page": i + 1
        }
        raw_recommendations = _make_authenticated_tmdb_api_request(f"{type.lower()}/{id}/recommendations", params=params).json().get("results")
        unsorted_recommendations.extend(raw_recommendations)

    sorted_recommendations = sorted(unsorted_recommendations, key=lambda x: x[sort_by], reverse=True if sort_dir == 'desc' else False)
    filtered_recos: List[TMDBMovieRecommendation | TMDBSeriesRecommendation] = [reco for reco in sorted_recommendations if reco['vote_count'] >= min_vote_count]
    
    return filtered_recos

def get_popular_series(excluded_tmdb_ids: List[str] | None = None) -> List[TMDBSeriesRecommendation]:
    # PER_PAGE = 20 # Determined by counting api response
    current_page = 1
    POPULAR_SERIES_COUNT = int(os.environ.get(CONFIG_KEYS["POPULAR_SERIES_COUNT"], 100))
    filtered_recos = []
    while len(filtered_recos) < POPULAR_SERIES_COUNT:
        params = {
            "page": current_page
        }
        recos_response = _make_authenticated_tmdb_api_request(f"tv/popular", params=params).json()
        recos = recos_response.get('results')
        if not recos:
            logger.error(f'Failed to fetch popular series due to TMDB API Failure: {recos_response}')
            logger.info(f'Continuing with popular series generation with only {len(filtered_recos)} recommendations.')
            break

        if not len(recos):
            logger.info(f'Cannot find anymore popular series. Stopping with {len(recos)} popular recommendations')
            break

        if excluded_tmdb_ids and len(excluded_tmdb_ids):
            filtered_recos.extend([reco for reco in recos if reco.get('id') not in excluded_tmdb_ids])
        else:
            filtered_recos.extend(recos)

        current_page = current_page + 1
    
    return filtered_recos[:POPULAR_SERIES_COUNT]

def get_popular_movies(excluded_tmdb_ids: List[str] | None = None) -> List[TMDBMovieRecommendation]:
    # PER_PAGE = 20 # Determined by counting api response
    current_page = 1
    POPULAR_MOVIES_COUNT = int(os.environ.get(CONFIG_KEYS["POPULAR_MOVIES_COUNT"], 50))
    filtered_recos = []
    while len(filtered_recos) < POPULAR_MOVIES_COUNT:
        params = {
            "page": current_page
        }
        recos_response = _make_authenticated_tmdb_api_request(f"movie/popular", params=params).json()
        recos = recos_response.get('results')
        if not recos:
            logger.error(f'Failed to fetch popular movies due to TMDB API Failure: {recos_response}')
            logger.info(f'Continuing with popular movies generation with only {len(filtered_recos)} recommendations.')
            break

        if not len(recos):
            logger.info(f'Cannot find anymore popular movies. Stopping with {len(recos)} popular recommendations')
            break
    
        if excluded_tmdb_ids and len(excluded_tmdb_ids):
            filtered_recos.extend([reco for reco in recos if reco.get('id') not in excluded_tmdb_ids])
        else:
            filtered_recos.extend(recos)

        current_page = current_page + 1
    
    return filtered_recos[:POPULAR_MOVIES_COUNT]

def get_upcoming_movies(excluded_tmdb_ids: List[str] | None = None) -> List[TMDBMovieRecommendation]:
    # PER_PAGE = 20 # Determined by counting api response
    current_page = 1
    UPCOMING_MOVIES_COUNT = int(os.environ.get(CONFIG_KEYS["UPCOMING_MOVIES_COUNT"], 50))
    filtered_recos = []
    while len(filtered_recos) < UPCOMING_MOVIES_COUNT:
        params = {
            "page": current_page
        }
        recos_response = _make_authenticated_tmdb_api_request(f"movie/upcoming", params=params).json()
        recos = recos_response.get('results')
        if not recos:
            logger.error(f'Failed to fetch upcoming movies due to TMDB API Failure: {recos_response}')
            logger.info(f'Continuing with upcoming movies generation with only {len(filtered_recos)} recommendations.')
            break
        if not len(recos):
            logger.info(f'Cannot find anymore upcoming movies. Stopping with {len(recos)} upcoming recommendations')
            break

        if excluded_tmdb_ids and len(excluded_tmdb_ids):
            filtered_recos.extend([reco for reco in recos if reco.get('id') not in excluded_tmdb_ids])
        else:
            filtered_recos.extend(recos)

        current_page = current_page + 1
    
    return filtered_recos[:UPCOMING_MOVIES_COUNT]
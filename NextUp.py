from services import jellyfinAPIService as jellyfin_api_service, tmdbAPIService as tmdb_api_service, watchstateAPIService as watchstate_api_service
from utils import helpers, filesystem, logger
from constants.config import CONFIG_KEYS
from constants.watchstate import WATCHSTATE_SECRET_KEYS
from adapters import jellyfin as jellyfin_adapter
import os
from datetime import datetime
from schemas.jellyfin.models import UserDto
from schemas.jellyfin.jellyfin import JellyfinMetadata
import math
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import time
from typing import List
from schemas.tmdb.models import TMDBSeriesRecommendation, TMDBMovieRecommendation
from collections import Counter

logger = logger.get_logger(__name__)

ROOT_RECOMMENDATIONS_DIR_PATH = None

def create_reco_dir():
    global ROOT_RECOMMENDATIONS_DIR_PATH
    PLACEHOLDER_MOVIE_FILE_PATH = os.environ.get(CONFIG_KEYS["PLACEHOLDER_FILE_PATH"], './movie.mp4')

    if not filesystem.does_path_exist(PLACEHOLDER_MOVIE_FILE_PATH):
        raise Exception(f"Placeholder movie file, ${PLACEHOLDER_MOVIE_FILE_PATH}, does not exist.")

    # Create NextUp dir in recommendations dir if it does not exist
    filesystem.create_directory(f"{ROOT_RECOMMENDATIONS_DIR_PATH}/NextUp")
    # Add copy of `movie.mp4` to it
    filesystem.copy_file(PLACEHOLDER_MOVIE_FILE_PATH, f"{ROOT_RECOMMENDATIONS_DIR_PATH}/NextUp/movie.mp4")

def get_all_user_watched_series(user: UserDto, max_days_lookback: int, min_episode_watch_count: int) -> List[watchstate_api_service.Series | jellyfin_api_service.Series]:
    global ROOT_RECOMMENDATIONS_DIR_PATH
        
    watched_series = None
    if os.environ.get(WATCHSTATE_SECRET_KEYS['WATCHSTATE_URL']) is not None:
        watched_series = watchstate_api_service.get_user_watched_series(user.get('Name').lower(), max_days_lookback, min_episode_watch_count)
    else:
        watched_series = jellyfin_api_service.get_user_watched_series_ids(helpers.convert_string_to_uuid(user.get("Id")), max_days_lookback, min_episode_watch_count)

    return watched_series

def write_recos_to_filesystem(base_path: str, metadata_json: List[JellyfinMetadata], type: str):
    if type.lower() not in ['movie', 'series']:
        raise Exception(f"Type must be one of [movie, series]. Got {type}")

    new_reco_dir_names = [f"{base_path}/{metadata.get('name')} ({datetime.strptime(metadata.get('firstAirDate' if type == 'series' else 'releaseDate'), "%Y-%m-%d").year})" for metadata in metadata_json]
    if filesystem.does_path_exist(f"{base_path}"):
        existing_recos_dirs = filesystem.get_all_dirs_in_dir(f"{base_path}")
        
        # Remove old recos
        for dir in existing_recos_dirs:
            if dir not in new_reco_dir_names:
                filesystem.recursively_rm_dir(dir)

    filesystem.create_directory(f"{base_path}")


    for metadata in metadata_json:
        release_year = datetime.strptime(metadata.get('firstAirDate' if type == 'series' else 'releaseDate'), "%Y-%m-%d").year
        dir_name = f"{base_path}/{metadata.get('name' if type == 'series' else 'title')} ({release_year})"
        filesystem.create_directory(f"{dir_name}")
        filesystem.save_json(f"{dir_name}/metadata.json", metadata)
        if type.lower() == 'series':
            filesystem.create_directory(f"{dir_name}/Season 00")
            filesystem.create_hard_link(f"{ROOT_RECOMMENDATIONS_DIR_PATH}/NextUp/movie.mp4", f"{dir_name}/Season 00/S00E9999.mp4")
        if type.lower() == 'movie':
            filesystem.create_hard_link(f"{ROOT_RECOMMENDATIONS_DIR_PATH}/NextUp/movie.mp4", f"{dir_name}/movie.mp4")


def weight_series_recos_by_watched_genres(watched_series: List[jellyfin_api_service.Series], series_recos: List[TMDBSeriesRecommendation]):
    series_genres = tmdb_api_service.get_tv_genres()
    series_genre_by_id_map = helpers.create_map_by_id(series_genres, 'id')

    genre_counts = Counter()
    for series in watched_series:
        genre_counts.update(series.genres)

    scored_recs = []
    for rec in series_recos:
        rec['genres'] = []
        for genre_id in rec['genre_ids']:
            rec['genres'].append(series_genre_by_id_map[genre_id].get('name'))

        score = sum(genre_counts.get(genre, 0) for genre in rec['genres'])
        scored_recs.append((score, rec))

    scored_recs.sort(key=lambda x: x[0], reverse=True)

    return [rec[1] for rec in scored_recs]

def weight_movie_recos_by_watched_genres(watched_movies: List[jellyfin_api_service.Movie], movie_recos: List[TMDBMovieRecommendation]):
    movie_genres = tmdb_api_service.get_movie_genres()
    movie_genre_by_id_map = helpers.create_map_by_id(movie_genres, 'id')

    genre_counts = Counter()
    for movie in watched_movies:
        genre_counts.update(movie.genres)

    scored_recs = []
    for rec in movie_recos:
        rec['genres'] = []
        for genre_id in rec['genre_ids']:
            rec['genres'].append(movie_genre_by_id_map[genre_id].get('name'))

        score = sum(genre_counts.get(genre, 0) for genre in rec['genres'])
        scored_recs.append((score, rec))

    scored_recs.sort(key=lambda x: x[0], reverse=True)

    return [rec[1] for rec in scored_recs]


def generate_movie_recommendations(user: UserDto, min_watch_percent: float, max_days_lookback: int, max_recos: int, max_total_recos: int):
    global ROOT_RECOMMENDATIONS_DIR_PATH
    
    all_user_movie_ids = jellyfin_api_service.get_all_available_movies(helpers.convert_string_to_uuid(user.get("Id")))

    watched_movies = None
    if os.environ.get(WATCHSTATE_SECRET_KEYS['WATCHSTATE_URL']) is not None:
        watched_movies = watchstate_api_service.get_user_watched_movies(user.get('Name').lower(), max_days_lookback)
    else:
        watched_movies = jellyfin_api_service.get_all_user_movies(helpers.convert_string_to_uuid(user.get("Id")), max_days_lookback, min_watch_percent)

    all_user_movie_ids.extend([series.tmdb_id for series in watched_movies])
    all_user_movie_ids = list(set(all_user_movie_ids))

    movie_recos = []
    for movie in watched_movies:
        recos = tmdb_api_service.get_recommendations_by_id('movie', movie.tmdb_id, sort_by='popularity', pages=math.ceil(max_recos/20))
        filtered_recos = [reco for reco in recos if reco.get('id') not in all_user_movie_ids]
        movie_recos.extend(filtered_recos[:max_recos])

    if max_total_recos:
        # Weight/sort all recos by user's most watched genres first. This really only matters if max_total_recos is set, otherwise all recos are used.
        weighted_recos = weight_movie_recos_by_watched_genres(watched_movies, movie_recos)

        # 90% of the recos will be from the user's most watched genres
        max_recos_count = min(max_total_recos, len(weighted_recos))
        first_90 = weighted_recos[:round(max_recos_count * 0.9)]

        # The last 10% will be from the least most watched
        last_10 = weighted_recos[-(max_recos_count - len(first_90)):]
        movie_recos = [*first_90, *last_10]

    metadata_json = [jellyfin_adapter.convert_movie_reco_to_metadata(reco) for reco in movie_recos]
    write_recos_to_filesystem(f"{ROOT_RECOMMENDATIONS_DIR_PATH}/{user["Name"]}/movies", metadata_json, 'movie')

def generate_series_recommendations(user: UserDto, max_days_lookback: int, max_recos: int, min_episode_watch_count: int, max_total_recos: int):
    global ROOT_RECOMMENDATIONS_DIR_PATH
    
    all_user_series_ids = jellyfin_api_service.get_all_available_series(helpers.convert_string_to_uuid(user.get("Id")))
    
    watched_series = get_all_user_watched_series(user, max_days_lookback, min_episode_watch_count)

    all_user_series_ids.extend([series.tmdb_id for series in watched_series])
    all_user_series_ids = list(set(all_user_series_ids))

    series_recos = []
    for series in watched_series:
        recos = tmdb_api_service.get_recommendations_by_id('tv', series.tmdb_id, pages=math.ceil(max_recos/20))
        filtered_recos = [reco for reco in recos if reco.get('id') not in all_user_series_ids]
        series_recos.extend(filtered_recos[:max_recos])

    if max_total_recos:
        # Weight/sort all recos by user's most watched genres first. This really only matters if max_total_recos is set, otherwise all recos are used.
        weighted_recos = weight_series_recos_by_watched_genres(watched_series, series_recos)

        # 90% of the recos will be from the user's most watched genres
        max_recos_count = min(max_total_recos, len(weighted_recos))
        first_90 = weighted_recos[:round(max_recos_count * 0.9)]

        # The last 10% will be from the least most watched
        last_10 = weighted_recos[-(max_recos_count - len(first_90)):]
        series_recos = [*first_90, *last_10]

    metadata_json = [jellyfin_adapter.convert_series_reco_to_metadata(reco) for reco in series_recos]
    write_recos_to_filesystem(f"{ROOT_RECOMMENDATIONS_DIR_PATH}/{user["Name"]}/series", metadata_json, 'series')
    
def generate_popular_series_recommendations():
    global ROOT_RECOMMENDATIONS_DIR_PATH

    # Get all series available on the server
    all_series_ids = jellyfin_api_service.get_all_available_series()

    # Get popular recos from TMDB (also filters out available media)
    popular_recos = tmdb_api_service.get_popular_series(all_series_ids)

    # Create metadata json for each reco
    metadata_json = [jellyfin_adapter.convert_series_reco_to_metadata(reco) for reco in popular_recos]
    # Write recos to filesystem
    write_recos_to_filesystem(f"{ROOT_RECOMMENDATIONS_DIR_PATH}/popular-series", metadata_json, 'series')

def generate_popular_movies_recommendations():
    global ROOT_RECOMMENDATIONS_DIR_PATH

    # Get all series available on the server
    all_movie_ids = jellyfin_api_service.get_all_available_movies()

    # Get popular recos from TMDB (also filters out available media)
    popular_recos = tmdb_api_service.get_popular_movies(all_movie_ids)

    # Create metadata json for each reco
    metadata_json = [jellyfin_adapter.convert_movie_reco_to_metadata(reco) for reco in popular_recos]
    
    # Write recos to filesystem
    write_recos_to_filesystem(f"{ROOT_RECOMMENDATIONS_DIR_PATH}/popular-movies", metadata_json, 'movie')

def generate_upcoming_movies_recommendations():
    global ROOT_RECOMMENDATIONS_DIR_PATH

    # Get all series available on the server
    all_movie_ids = jellyfin_api_service.get_all_available_movies()

    # Get popular recos from TMDB (also filters out available media)
    popular_recos = tmdb_api_service.get_upcoming_movies(all_movie_ids)

    # Create metadata json for each reco
    metadata_json = [jellyfin_adapter.convert_movie_reco_to_metadata(reco) for reco in popular_recos]
    
    # Write recos to filesystem
    write_recos_to_filesystem(f"{ROOT_RECOMMENDATIONS_DIR_PATH}/upcoming-movies", metadata_json, 'movie')

def log_time():
    logger.info(f"Generating recommendations at {time.strftime('%H:%M:%S')}")

def NextUp():
    global ROOT_RECOMMENDATIONS_DIR_PATH
    ROOT_RECOMMENDATIONS_DIR_PATH = os.environ.get(CONFIG_KEYS["NEXTUP_RECOMMENDATIONS_DIR"], '/recommendations')
    GENERATE_RECOS_FOR = os.environ.get(CONFIG_KEYS["GENERATE_RECOS_FOR"], '')
    generate_recos_for_list = [name.lower() for name in GENERATE_RECOS_FOR.rsplit(',')]
    filtered_generated_recos_for_list = [name for name in generate_recos_for_list if name]
    
    DISABLE_MOVIE_RECOMMENDATIONS = os.environ.get(CONFIG_KEYS['DISABLE_MOVIE_RECOMMENDATIONS']).lower() == 'true'
    MIN_MOVIE_WATCH_PERCENT = os.environ.get(CONFIG_KEYS["MIN_MOVIE_WATCH_PERCENT"])
    MAX_MOVIE_DAYS_LOOKBACK = os.environ.get(CONFIG_KEYS['MAX_MOVIE_DAYS_LOOKBACK'])
    MAX_RECOMMENDATIONS_PER_MOVIE = os.environ.get(CONFIG_KEYS['MAX_RECOMMENDATIONS_PER_MOVIE'], 5)
    MAX_TOTAL_MOVIE_RECOMMENDATIONS = os.environ.get(CONFIG_KEYS['MAX_TOTAL_MOVIE_RECOMMENDATIONS'])
    INCLUDE_UPCOMING_MOVIE_RECOMMENDATIONS = os.environ.get(CONFIG_KEYS['INCLUDE_UPCOMING_MOVIE_RECOMMENDATIONS']).lower() == 'true'
    INCLUDE_POPULAR_MOVIE_RECOMMENDATIONS = os.environ.get(CONFIG_KEYS['INCLUDE_POPULAR_MOVIE_RECOMMENDATIONS']).lower() == 'true'

    DISABLE_SERIES_RECOMMENDATIONS = os.environ.get(CONFIG_KEYS['DISABLE_SERIES_RECOMMENDATIONS']).lower() == 'true'
    MAX_SERIES_DAYS_LOOKBACK = os.environ.get(CONFIG_KEYS['MAX_SERIES_DAYS_LOOKBACK'])
    MAX_RECOMMENDATIONS_PER_SERIES = os.environ.get(CONFIG_KEYS['MAX_RECOMMENDATIONS_PER_SERIES'], 10)
    MIN_EPISODE_WATCH_COUNT = os.environ.get(CONFIG_KEYS['MIN_EPISODE_WATCH_COUNT'], 2)
    MAX_TOTAL_SERIES_RECOMMENDATIONS = os.environ.get(CONFIG_KEYS['MAX_TOTAL_SERIES_RECOMMENDATIONS'])
    INCLUDE_POPULAR_SERIES_RECOMMENDATIONS = os.environ.get(CONFIG_KEYS['INCLUDE_POPULAR_SERIES_RECOMMENDATIONS'], 'true').lower() == 'true'    

    all_jellyfin_users = jellyfin_api_service.get_users()
    users_to_recommend_for = [user for user in all_jellyfin_users if user["Name"].lower() in filtered_generated_recos_for_list or len(filtered_generated_recos_for_list) == 0]

    if not users_to_recommend_for or not len(users_to_recommend_for):
        raise Exception('No users defined. Stopping.')
    
    create_reco_dir()

    for user in users_to_recommend_for:
        if not DISABLE_MOVIE_RECOMMENDATIONS:
            generate_movie_recommendations(user, float(MIN_MOVIE_WATCH_PERCENT), int(MAX_MOVIE_DAYS_LOOKBACK), int(MAX_RECOMMENDATIONS_PER_MOVIE), int(MAX_TOTAL_MOVIE_RECOMMENDATIONS))
        else:
            logger.info("Movie recommendations are disabled. Skipping.")
        
        if not DISABLE_SERIES_RECOMMENDATIONS:
            generate_series_recommendations(user, int(MAX_SERIES_DAYS_LOOKBACK), int(MAX_RECOMMENDATIONS_PER_SERIES), int(MIN_EPISODE_WATCH_COUNT), int(MAX_TOTAL_SERIES_RECOMMENDATIONS))
        else:
            logger.info("Series recommendations are disabled. Skipping.")

    if INCLUDE_POPULAR_SERIES_RECOMMENDATIONS:
        generate_popular_series_recommendations()

    if INCLUDE_POPULAR_MOVIE_RECOMMENDATIONS:
        generate_popular_movies_recommendations()
    
    if INCLUDE_UPCOMING_MOVIE_RECOMMENDATIONS:
        generate_upcoming_movies_recommendations()

def start_main_loop():
    time.tzset()
    RECOMMENDATIONS_CRON_SCHEDULE = os.environ.get(CONFIG_KEYS["RECOMMENDATIONS_CRON_SCHEDULE"])
    if not RECOMMENDATIONS_CRON_SCHEDULE:
        logger.info("Found no cron schedule for recommendations. Not starting recommendations engine.")
        return None
    else:
        logger.info(f"Using {RECOMMENDATIONS_CRON_SCHEDULE} cron schedule")

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        NextUp,
        CronTrigger.from_crontab(RECOMMENDATIONS_CRON_SCHEDULE),
        id="recos"
    )

    scheduler.start()

    return scheduler
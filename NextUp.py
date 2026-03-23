from services import jellyfinAPIService as jellyfin_api_service, tmdbAPIService as tmdb_api_service, seerrAPIService as seerr_api_service
from utils import load_env, helpers, filesystem
from constants.config import CONFIG_KEYS
from adapters import jellyfin as jellyfin_adapter
import os
from datetime import datetime
from typing import List
from schemas.jellyfin.models import UserDto
import math
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import time


ROOT_RECOMMENDATIONS_DIR_PATH = None

def create_reco_dir():
    global ROOT_RECOMMENDATIONS_DIR_PATH

    # Create NextUp dir in recommendations dir if it does not exist
    filesystem.create_directory(f"{ROOT_RECOMMENDATIONS_DIR_PATH}/NextUp")
    # Add copy of `movie.mp4` to it
    filesystem.copy_file('./movie.mp4', f"{ROOT_RECOMMENDATIONS_DIR_PATH}/NextUp")

def generateMovieRecommendations(user: UserDto, min_watch_percent: float, max_days_lookback: int, max_recos: int):
    global ROOT_RECOMMENDATIONS_DIR_PATH
    
    all_user_movie_ids = jellyfin_api_service.get_all_available_movies(helpers.convert_string_to_uuid(user.get("Id")))
    watched_movies = jellyfin_api_service.get_all_user_movies(helpers.convert_string_to_uuid(user.get("Id")), max_days_lookback, min_watch_percent)
    movie_recos = []
    for movie in watched_movies:
        recos = tmdb_api_service.get_recommendations_by_id('movie', movie.tmdb_id, sort_by='popularity', pages=math.ceil(max_recos/20))
        filtered_recos = [reco for reco in recos if reco.get('id') not in all_user_movie_ids]
        movie_recos.extend(filtered_recos[:max_recos])

    metadata_json = [jellyfin_adapter.convert_movie_reco_to_metadata(reco) for reco in movie_recos]
    new_reco_dir_names = [f"{ROOT_RECOMMENDATIONS_DIR_PATH}/{user["Name"]}/movies/{metadata.get('title')} ({datetime.strptime(metadata.get('releaseDate'), "%Y-%m-%d").year})" for metadata in metadata_json]

    if filesystem.does_path_exist(f"{ROOT_RECOMMENDATIONS_DIR_PATH}/{user["Name"]}/movies"):
        existing_recos_dirs = filesystem.get_all_dirs_in_dir(f"{ROOT_RECOMMENDATIONS_DIR_PATH}/{user["Name"]}/movies")
        # Remove old recos
        for dir in existing_recos_dirs:
            if dir not in new_reco_dir_names:
                filesystem.recursively_rm_dir(dir)

    filesystem.create_directory(f"{ROOT_RECOMMENDATIONS_DIR_PATH}/{user["Name"]}/movies")

    for metadata in metadata_json:
        release_year = datetime.strptime(metadata.get('releaseDate'), "%Y-%m-%d").year
        dir_name = f"{user["Name"]}/movies/{metadata.get('title')} ({release_year})"
        if f"{ROOT_RECOMMENDATIONS_DIR_PATH}/{user["Name"]}/{dir_name}" not in new_reco_dir_names:
            filesystem.create_directory(f"{ROOT_RECOMMENDATIONS_DIR_PATH}/{dir_name}")
            filesystem.save_json(f"{ROOT_RECOMMENDATIONS_DIR_PATH}/{dir_name}/metadata.json", metadata)
            filesystem.create_hard_link(f"{ROOT_RECOMMENDATIONS_DIR_PATH}/NextUp/movie.mp4", f"{ROOT_RECOMMENDATIONS_DIR_PATH}/{dir_name}/movie.mp4")


    return

def generateSeriesRecommendations(user: UserDto, max_days_lookback: int, max_recos: int):
    global ROOT_RECOMMENDATIONS_DIR_PATH
    
    all_user_series_ids = jellyfin_api_service.get_all_available_series(helpers.convert_string_to_uuid(user.get("Id")))
    watched_series = jellyfin_api_service.get_user_watched_series_ids(helpers.convert_string_to_uuid(user.get("Id")), max_days_lookback)

    series_recos = []
    for series in watched_series:
        recos = tmdb_api_service.get_recommendations_by_id('tv', series.tmdb_id, sort_by='popularity', pages=math.ceil(max_recos/20))
        filtered_recos = [reco for reco in recos if reco.get('id') not in all_user_series_ids]
        series_recos.extend(filtered_recos[:max_recos])

    metadata_json = [jellyfin_adapter.convert_series_reco_to_metadata(reco) for reco in series_recos]
    new_reco_dir_names = [f"{ROOT_RECOMMENDATIONS_DIR_PATH}/{user["Name"]}/series/{metadata.get('name')} ({datetime.strptime(metadata.get('firstAirDate'), "%Y-%m-%d").year})" for metadata in metadata_json]

    if filesystem.does_path_exist(f"{ROOT_RECOMMENDATIONS_DIR_PATH}/{user["Name"]}/series"):
        existing_recos_dirs = filesystem.get_all_dirs_in_dir(f"{ROOT_RECOMMENDATIONS_DIR_PATH}/{user["Name"]}/series")
        
        # Remove old recos
        for dir in existing_recos_dirs:
            if dir not in new_reco_dir_names:
                filesystem.recursively_rm_dir(dir)

    filesystem.create_directory(f"{ROOT_RECOMMENDATIONS_DIR_PATH}/{user["Name"]}/series")

    for metadata in metadata_json:
        release_year = datetime.strptime(metadata.get('firstAirDate'), "%Y-%m-%d").year
        dir_name = f"{user["Name"]}/series/{metadata.get('name')} ({release_year})"
        if f"{ROOT_RECOMMENDATIONS_DIR_PATH}/{user["Name"]}/{dir_name}" not in new_reco_dir_names:
            filesystem.create_directory(f"{ROOT_RECOMMENDATIONS_DIR_PATH}/{dir_name}")
            filesystem.save_json(f"{ROOT_RECOMMENDATIONS_DIR_PATH}/{dir_name}/metadata.json", metadata)
            filesystem.create_directory(f"{ROOT_RECOMMENDATIONS_DIR_PATH}/{dir_name}/Season 00")
            filesystem.create_hard_link(f"{ROOT_RECOMMENDATIONS_DIR_PATH}/NextUp/movie.mp4", f"{ROOT_RECOMMENDATIONS_DIR_PATH}/{dir_name}/Season 00/S00E9999.mp4")

def log_time():
    print(f"Generating recommendations at {time.strftime('%H:%M:%S')}")

def NextUp():
    global ROOT_RECOMMENDATIONS_DIR_PATH
    ROOT_RECOMMENDATIONS_DIR_PATH = os.environ.get(CONFIG_KEYS["NEXTUP_RECOMMENDATIONS_DIR"])
    GENERATE_RECOS_FOR = [name.lower() for name in os.environ.get(CONFIG_KEYS["GENERATE_RECOS_FOR"]).rsplit(',')]
    MIN_MOVIE_WATCH_PERCENT = os.environ.get(CONFIG_KEYS["MIN_MOVIE_WATCH_PERCENT"])
    MAX_MOVIE_DAYS_LOOKBACK = os.environ.get(CONFIG_KEYS['MAX_MOVIE_DAYS_LOOKBACK'])
    MAX_RECOMMENDATIONS_PER_MOVIE = os.environ.get(CONFIG_KEYS['MAX_RECOMMENDATIONS_PER_MOVIE'])

    MAX_SERIES_DAYS_LOOKBACK = os.environ.get(CONFIG_KEYS['MAX_SERIES_DAYS_LOOKBACK'])
    MAX_RECOMMENDATIONS_PER_SERIES = os.environ.get(CONFIG_KEYS['MAX_RECOMMENDATIONS_PER_SERIES'])
    
    DISABLE_MOVIE_RECOMMENDATIONS = True if os.environ.get(CONFIG_KEYS['DISABLE_MOVIE_RECOMMENDATIONS']).lower() == 'true' else False
    DISABLE_SERIES_RECOMMENDATIONS = True if os.environ.get(CONFIG_KEYS['DISABLE_SERIES_RECOMMENDATIONS']).lower() == 'true' else False

    all_jellyfin_users = jellyfin_api_service.get_users()
    users_to_recommend_for = [user for user in all_jellyfin_users if user["Name"].lower() in GENERATE_RECOS_FOR]

    if not users_to_recommend_for or not len(users_to_recommend_for):
        raise Exception('No users defined. Stopping.')
    
    create_reco_dir()

    for user in users_to_recommend_for:
        if not DISABLE_MOVIE_RECOMMENDATIONS:
            generateMovieRecommendations(user, float(MIN_MOVIE_WATCH_PERCENT), int(MAX_MOVIE_DAYS_LOOKBACK), int(MAX_RECOMMENDATIONS_PER_MOVIE))
        else:
            print("Movie recommendations are disabled. Skipping.")
        
        if not DISABLE_SERIES_RECOMMENDATIONS:
            generateSeriesRecommendations(user, int(MAX_SERIES_DAYS_LOOKBACK), int(MAX_RECOMMENDATIONS_PER_SERIES))
        else:
            print("Series recommendations are disabled. Skipping.")

def start_main_loop():
    time.tzset()
    RECOMMENDATIONS_CRON_SCHEDULE = os.environ.get(CONFIG_KEYS["RECOMMENDATIONS_CRON_SCHEDULE"])
    if not RECOMMENDATIONS_CRON_SCHEDULE:
        print("Found no cron schedule for recommendations. Not starting recommendations engine.")
        return None
    else:
        print(f"Using {RECOMMENDATIONS_CRON_SCHEDULE} cron schedule")

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        NextUp,
        CronTrigger.from_crontab(RECOMMENDATIONS_CRON_SCHEDULE),
        id="recos"
    )

    scheduler.start()

    return scheduler
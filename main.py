from services import jellyfin as jellyfin_service, tmdb as tmdb_service
from utils import load_env, helpers, filesystem
from constants.config import CONFIG_KEYS
from adapters import jellyfin as jellyfin_adapter
import os
from datetime import datetime
 


load_env.load_env()
all_users = jellyfin_service.get_users()
admin_user = next(user for user in all_users if user["Name"].lower() == 'admin')

if not admin_user:
    raise 'Failed to find admin user'

ROOT_RECOMMENDATIONS_DIR_PATH = os.environ.get(CONFIG_KEYS["JELLYFIN_RECOMMENDATIONS_DIR"])

# Create NextUp dir in recommendations dir if it does not exist
filesystem.create_directory(f"{ROOT_RECOMMENDATIONS_DIR_PATH}/NextUp")
# Add copy of `movie.mp4` to it
filesystem.copy_file('./movie.mp4', f"{ROOT_RECOMMENDATIONS_DIR_PATH}/NextUp")

all_movie_ids = jellyfin_service.get_all_available_movies()

watched_movies = jellyfin_service.get_all_user_movies(helpers.convert_string_to_uuid(admin_user.get("Id")), None, 99)
movie_recos = []
for movie in watched_movies:
    recos = tmdb_service.get_recommendations_by_id('movie', movie.tmdb_id, sort_by='popularity', pages=1)
    filtered_recos = [reco for reco in recos if reco.get('id') not in all_movie_ids]
    movie_recos.extend(filtered_recos)

metadata_json = [jellyfin_adapter.convert_movie_reco_to_metadata(reco) for reco in movie_recos]


existing_recos_dirs = filesystem.get_all_dirs_in_dir(f"{ROOT_RECOMMENDATIONS_DIR_PATH}/{admin_user["Name"]}")
new_reco_dir_names = [f"{ROOT_RECOMMENDATIONS_DIR_PATH}/{admin_user["Name"]}/{metadata.get('title')} ({datetime.strptime(metadata.get('releaseDate'), "%Y-%m-%d").year})" for metadata in metadata_json]

# Remove old recos
for dir in existing_recos_dirs:
    if dir not in new_reco_dir_names:
        filesystem.recursively_rm_dir(dir)

filesystem.create_directory(f"{ROOT_RECOMMENDATIONS_DIR_PATH}/{admin_user["Name"]}")
for metadata in metadata_json:
    release_year = datetime.strptime(metadata.get('releaseDate'), "%Y-%m-%d").year
    dir_name = f"{admin_user["Name"]}/{metadata.get('title')} ({release_year})"
    if f"{ROOT_RECOMMENDATIONS_DIR_PATH}/{admin_user["Name"]}/{dir_name}" not in new_reco_dir_names:
        filesystem.create_directory(f"{ROOT_RECOMMENDATIONS_DIR_PATH}/{dir_name}")
        filesystem.save_json(f"{ROOT_RECOMMENDATIONS_DIR_PATH}/{dir_name}/metadata.json", metadata)
        filesystem.create_hard_link(f"{ROOT_RECOMMENDATIONS_DIR_PATH}/NextUp/movie.mp4", f"{ROOT_RECOMMENDATIONS_DIR_PATH}/{dir_name}/movie.mp4")

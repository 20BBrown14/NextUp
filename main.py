from services import jellyfin as jellyfin_service
from utils.load_env import load_env

load_env()
watched_series = jellyfin_service.get_user_watched_series_ids('d2601d14-3074-4733-859a-053c0882b78d')
print(watched_series)
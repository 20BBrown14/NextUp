from fastapi import FastAPI, APIRouter, Request, HTTPException
from pydantic import BaseModel
from constants.jellyfin import WEBHOOK_NOTIFICATION_TYPES, SUPPORTED_WEBHOOK_NOTIFICATION_TYPES
from services import jellyfinAPIService as jellyfin_api_service, seerrAPIService as seerr_api_service
from utils import load_env
from NextUp import start_main_loop, NextUp
from utils.logger import get_logger

logger = get_logger(__name__)

class JellyfinWebhook(BaseModel):
    ServerId: str | None = None
    ServerName: str | None = None
    ServerVersion: str | None = None
    ServerUrl: str | None = None
    NotificationType: str | None = None
    Timestamp: str | None = None
    UtcTimestamp: str | None = None
    Name: str | None = None
    Overview: str | None = None
    Tagline: str | None = None
    ItemId: str | None = None
    ItemType: str | None = None
    RunTimeTicks: int | None = None
    RunTime: str | None = None
    Year: int | None = None
    PremiereDate: str | None = None
    Genres: str | None = None # comma separated list
    Provider_imdb: str | None = None
    Provider_tmdb: str | None = None
    Provider_tmdbcollection: str | None = None
    Provider_tvrage: str | None = None
    Provider_tvdb: str | None = None
    Likes: bool | None = None
    Rating: int | None = None
    PlaybackPositionTicks: int | None = None
    PlaybackPosition: str | None = None
    PlayCount: int | None = None
    Favorite: bool | None = None
    Played: bool | None = None
    AutdioStreamIndex: int | None = None
    SubtitleStreamIndex: int | None = None
    SaveReason: str | None = None
    NotificationUsername: str | None = None
    UserId: str | None = None

async def lifespan(app: FastAPI):
    load_env.load_env()

    scheduler = start_main_loop()
    yield
    scheduler.shutdown()

app = FastAPI(lifespan=lifespan)
router = APIRouter()

@router.get("/health-check")
async def health_check(request: Request):
    return {"message": "Healthy!"}

@router.post("/recommendations/run")
async def run_all_recommendations(request: Request):
    NextUp()

@router.post("/webhook/jellyfin/")
async def webhook_test(request: Request):
    raw_request_body = await request.json()
    request_body = JellyfinWebhook(**raw_request_body)
    tmdb_id, request_user_id, favorite, notification_type, item_type, item_id = request_body.Provider_tmdb, request_body.UserId, request_body.Favorite, request_body.NotificationType, request_body.ItemType, request_body.ItemId

    if(notification_type not in SUPPORTED_WEBHOOK_NOTIFICATION_TYPES):
        raise HTTPException(status_code=400, detail=f"Got unexpected notification type: {notification_type}")
    
    match notification_type:
        case 'UserDataSaved':
            logger.info(f"Got {notification_type} event.")
        case _:
            raise HTTPException(status_code=500, detail="An unrecoverable server error occured. Please try again later.")
        
    if not favorite:
        logger.info("Got event for user removing media from favorites. Ignoring.")
        return 
    
    media_type_tmdb_ids = []
    if item_type.lower() == 'movie':
        media_type_tmdb_ids = jellyfin_api_service.get_all_available_movies()
    elif item_type.lower() == 'series':
        media_type_tmdb_ids = jellyfin_api_service.get_all_available_series()

    if int(tmdb_id) in media_type_tmdb_ids:
        logger.info(f"TMDB ID {tmdb_id} is already available on server.")
        return {"message": "Success"}        
    
    seerr_users = seerr_api_service.get_seerr_users()
    request_user = next(user for user in seerr_users if user['jellyfinUserId'] == request_user_id)

    if not request_user:
        logger.error(f"Unable to find seerr user with Jellyfin user id {request_user_id}")
        raise HTTPException(status_code=400, detail=f"Unable to find seerr user with Jellyfin user id {request_user_id}")

    media_request = seerr_api_service.make_media_request(int(tmdb_id), request_user['id'], 'movie' if item_type.lower() == 'movie' else 'tv')
    logger.info(f"Request for tmdb id {tmdb_id} created with id {media_request['id']}")

    jellyfin_api_service.delete_item_by_id(item_id)
    return {"message": "Success"}

app.include_router(router)
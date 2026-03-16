from schemas.tmdb.models import TMDBRecommendation
from schemas.jellyfin.jellyfin import JellyfinMetadata
from datetime import datetime

def convert_movie_reco_to_metadata(reco: TMDBRecommendation) -> JellyfinMetadata:
    today = datetime.today()
    
    return {
        "mediaInfo": None,
        "mediaType": 0,
        "releaseDate": reco.get('release_date'),
        "genreIds": reco.get('genre_ids'),
        "originalLanguage": reco.get('original_language'),
        "originalName": reco.get('original_title'),
        "voteAverage": reco.get('vote_average'),
        "voteCount": reco.get('vote_count'),
        "backdropPath": reco.get('backdrop_path'),
        "posterPath": reco.get('poster_path'),
        "extraId": None,
        "extraIdName": 'tvdbid',
        "createdDate": f"{today.isoformat()}+00:00",
        "networkTag": None,
        "networkId": None,
        "title": reco.get('title'),
        "id": reco.get('id'),
        "popularity": reco.get('popularity'),
        "overview": reco.get('overview'),
        "adult": reco.get('adult'),
        "video": reco.get('video')
    }
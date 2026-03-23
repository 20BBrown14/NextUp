from schemas.tmdb.models import TMDBMovieRecommendation, TMDBSeriesRecommendation
from schemas.jellyfin.jellyfin import JellyfinMetadata
from datetime import datetime

def convert_movie_reco_to_metadata(reco: TMDBMovieRecommendation) -> JellyfinMetadata:
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

def convert_series_reco_to_metadata(reco: TMDBSeriesRecommendation) -> JellyfinMetadata:
    today = datetime.today()
    
    return {
        "mediaInfo": None,
        "mediaType": 1,
        "firstAirDate": reco.get('first_air_date'),
        "genreIds": reco.get('genre_ids'),
        "originCountry": reco.get('origin_country'),
        "originalLangugage": reco.get('original_language'),
        "voteAverage": reco.get('vote_average'),
        "voteCount": reco.get('vote_count'),
        "backdropPath": reco.get('backdrop_path'),
        "posterPath": reco.get('poster_path'),
        "extraId": None,
        "extraIdName": "tvdbid",
        "createdDate": f"{today.isoformat()}+00:00",
        "networkTag": None,
        "networkId": None,
        "name": reco.get('name'),
        "id": reco.get('id'),
        "popularity": reco.get('popularity'),
        "overview": reco.get('overview')
    }
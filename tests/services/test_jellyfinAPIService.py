import unittest
from unittest.mock import patch, MagicMock, call
import os
from datetime import date, timedelta
from services.jellyfinAPIService import (
    get_users,
    get_configured_users,
    get_series_provider_ids_by_ids,
    get_movies_provider_ids_by_ids,
    get_series_genres_by_ids,
    get_movie_genres_by_ids,
    get_user_watched_series_ids,
    get_user_fully_watched_movies,
    get_user_in_progress_movies,
    get_all_user_movies,
    get_all_available_movies,
    get_all_available_series,
    delete_item_by_id,
    get_item_path,
    get_items_by_tmdb_ids,
    get_series_episode_paths,
    get_virtual_folders,
    get_virtual_folder_by_name,
    create_library,
    refresh_libraries,
    get_user_policy,
    add_library_to_user,
    get_collections,
    get_collection_by_name,
    get_collection_items,
    create_collection,
    add_items_to_collection,
    remove_items_from_collection,
    COLLECTION_ITEMS_BATCH_SIZE,
    DEFAULT_LIBRARY_OPTIONS,
    _make_authenticated_jellyfin_api_request,
    _select_library_scoping_user,
    _library_cache,
    _item_meta_cache,
    _user_cache,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_response(data) -> MagicMock:
    """Return a mock requests.Response whose .json() yields *data*."""
    mock = MagicMock()
    mock.json.return_value = data
    return mock


def _make_episode(
    series_name: str = 'Test Series',
    series_id: str = 'series-id-1',
    last_played_date: str = None,
) -> dict:
    today = date.today()
    return {
        'SeriesName': series_name,
        'SeriesId': series_id,
        'UserData': {
            'LastPlayedDate': f"{last_played_date or today.isoformat()}T00:00:00.0000000Z"
        }
    }


def _make_movie_item(
    name: str = 'Test Movie',
    item_id: str = 'abc12345678901234567890123456789',
    tmdb_id: str = '12345',
    last_played_date: str = None,
    played_percentage: float = 100.0,
) -> dict:
    today = date.today()
    return {
        'Name': name,
        'Id': item_id,
        'ProviderIds': {'Tmdb': tmdb_id},
        'UserData': {
            'LastPlayedDate': f"{last_played_date or today.isoformat()}T00:00:00.0000000Z",
            'PlayedPercentage': played_percentage,
        }
    }


def _make_library_item(tmdb_id: str = '999') -> dict:
    return {'ProviderIds': {'Tmdb': tmdb_id}}


# ---------------------------------------------------------------------------
# Base class – clears all caches before every test
# ---------------------------------------------------------------------------

class JellyfinTestBase(unittest.TestCase):
    def setUp(self):
        _library_cache.clear()
        _item_meta_cache.clear()
        _user_cache.clear()


# ===========================================================================
# _make_authenticated_jellyfin_api_request
# ===========================================================================

class TestMakeAuthenticatedJellyfinApiRequest(JellyfinTestBase):

    @patch('services.jellyfinAPIService.make_request')
    def test_builds_url_from_env(self, mock_make_request):
        mock_make_request.return_value = MagicMock()
        with patch.dict(os.environ, {'JELLYFIN_API_KEY': 'key', 'JELLYFIN_URL': 'http://jellyfin.local'}):
            _make_authenticated_jellyfin_api_request('Users')
        url = mock_make_request.call_args[0][0]
        self.assertEqual(url, 'http://jellyfin.local/Users')

    @patch('services.jellyfinAPIService.make_request')
    def test_injects_mediabrowser_auth_header(self, mock_make_request):
        mock_make_request.return_value = MagicMock()
        with patch.dict(os.environ, {'JELLYFIN_API_KEY': 'my-token', 'JELLYFIN_URL': 'http://jf'}):
            _make_authenticated_jellyfin_api_request('Users')
        headers = mock_make_request.call_args[0][4]
        self.assertEqual(headers['Authorization'], 'MediaBrowser Token="my-token"')

    @patch('services.jellyfinAPIService.make_request')
    def test_merges_extra_headers(self, mock_make_request):
        mock_make_request.return_value = MagicMock()
        with patch.dict(os.environ, {'JELLYFIN_API_KEY': 'k', 'JELLYFIN_URL': 'http://jf'}):
            _make_authenticated_jellyfin_api_request('Users', headers={'X-Custom': 'yes'})
        headers = mock_make_request.call_args[0][4]
        self.assertEqual(headers['X-Custom'], 'yes')
        self.assertIn('Authorization', headers)

    @patch('services.jellyfinAPIService.make_request')
    def test_passes_params_body_and_method(self, mock_make_request):
        mock_make_request.return_value = MagicMock()
        with patch.dict(os.environ, {'JELLYFIN_API_KEY': 'k', 'JELLYFIN_URL': 'http://jf'}):
            _make_authenticated_jellyfin_api_request('Items', method='POST', params={'p': 1}, body={'b': 2})
        args = mock_make_request.call_args[0]
        self.assertEqual(args[1], 'POST')
        self.assertEqual(args[2], {'p': 1})
        self.assertEqual(args[3], {'b': 2})


# ===========================================================================
# get_users
# ===========================================================================

class TestGetUsers(JellyfinTestBase):

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_returns_user_list(self, mock_req):
        users = [{'Id': '1', 'Name': 'Alice'}, {'Id': '2', 'Name': 'Bob'}]
        mock_req.return_value = _make_mock_response(users)
        result = get_users()
        self.assertEqual(result, users)

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_calls_correct_endpoint(self, mock_req):
        mock_req.return_value = _make_mock_response([])
        get_users()
        mock_req.assert_called_once_with('Users')

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_result_is_cached(self, mock_req):
        mock_req.return_value = _make_mock_response([{'Id': '1', 'Name': 'Alice'}])
        get_users()
        get_users()
        mock_req.assert_called_once()


# ===========================================================================
# get_configured_users
# ===========================================================================

class TestGetConfiguredUsers(JellyfinTestBase):

    @patch('services.jellyfinAPIService.get_users')
    def test_filters_by_configured_usernames_case_insensitive(self, mock_get_users):
        mock_get_users.return_value = [
            {'Id': '1', 'Name': 'Alice'},
            {'Id': '2', 'Name': 'Bob'},
            {'Id': '3', 'Name': 'Carol'},
        ]
        with patch.dict(os.environ, {'JELLYFIN_USERS': 'alice,carol'}):
            result = get_configured_users()
        names = [u['Name'] for u in result]
        self.assertIn('Alice', names)
        self.assertIn('Carol', names)
        self.assertNotIn('Bob', names)

    @patch('services.jellyfinAPIService.get_users')
    def test_returns_empty_when_no_match(self, mock_get_users):
        mock_get_users.return_value = [{'Id': '1', 'Name': 'Alice'}]
        with patch.dict(os.environ, {'JELLYFIN_USERS': 'nobody'}):
            result = get_configured_users()
        self.assertEqual(result, [])

    @patch('services.jellyfinAPIService.get_users')
    def test_handles_uppercase_configured_names(self, mock_get_users):
        mock_get_users.return_value = [{'Id': '1', 'Name': 'Bob'}]
        with patch.dict(os.environ, {'JELLYFIN_USERS': 'BOB'}):
            result = get_configured_users()
        self.assertEqual(len(result), 1)


# ===========================================================================
# get_series_provider_ids_by_ids
# ===========================================================================

class TestGetSeriesProviderIdsByIds(JellyfinTestBase):

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_returns_tmdb_ids(self, mock_req):
        mock_req.return_value = _make_mock_response({
            'Items': [
                {'ProviderIds': {'Tmdb': '101'}},
                {'ProviderIds': {'Tmdb': '202'}},
            ]
        })
        result = get_series_provider_ids_by_ids(['id1', 'id2'])
        self.assertEqual(result, ['101', '202'])

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_skips_items_without_tmdb_id(self, mock_req):
        mock_req.return_value = _make_mock_response({
            'Items': [
                {'ProviderIds': {}},
                {'ProviderIds': {'Tmdb': '303'}},
            ]
        })
        result = get_series_provider_ids_by_ids(['id1', 'id2'])
        self.assertEqual(result, ['303'])

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_passes_correct_params(self, mock_req):
        mock_req.return_value = _make_mock_response({'Items': []})
        get_series_provider_ids_by_ids(['aaa', 'bbb'])
        params = mock_req.call_args[1].get('params') or mock_req.call_args[0][2]
        self.assertEqual(params['Fields'], 'ProviderIds')
        self.assertEqual(params['ids'], 'aaa,bbb')

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_result_is_cached(self, mock_req):
        mock_req.return_value = _make_mock_response({'Items': [{'ProviderIds': {'Tmdb': '1'}}]})
        get_series_provider_ids_by_ids(['x'])
        get_series_provider_ids_by_ids(['x'])
        mock_req.assert_called_once()


# ===========================================================================
# get_movies_provider_ids_by_ids
# ===========================================================================

class TestGetMoviesProviderIdsByIds(JellyfinTestBase):

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_returns_tmdb_ids(self, mock_req):
        mock_req.return_value = _make_mock_response({
            'Items': [
                {'ProviderIds': {'Tmdb': '500'}},
                {'ProviderIds': {'Tmdb': '600'}},
            ]
        })
        result = get_movies_provider_ids_by_ids(['m1', 'm2'])
        self.assertEqual(result, ['500', '600'])

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_skips_items_without_tmdb_id(self, mock_req):
        mock_req.return_value = _make_mock_response({
            'Items': [
                {'ProviderIds': {}},
                {'ProviderIds': {'Tmdb': '700'}},
            ]
        })
        result = get_movies_provider_ids_by_ids(['m1', 'm2'])
        self.assertEqual(result, ['700'])

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_result_is_cached(self, mock_req):
        mock_req.return_value = _make_mock_response({'Items': [{'ProviderIds': {'Tmdb': '1'}}]})
        get_movies_provider_ids_by_ids(['m1'])
        get_movies_provider_ids_by_ids(['m1'])
        mock_req.assert_called_once()


# ===========================================================================
# get_series_genres_by_ids
# ===========================================================================

class TestGetSeriesGenresByIds(JellyfinTestBase):

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_returns_lowercased_genre_lists(self, mock_req):
        mock_req.return_value = _make_mock_response({
            'Items': [
                {'Genres': ['Action', 'Drama']},
                {'Genres': ['Comedy']},
            ]
        })
        result = get_series_genres_by_ids(['s1', 's2'])
        self.assertEqual(result, [['action', 'drama'], ['comedy']])

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_returns_empty_inner_list_for_item_with_no_genres(self, mock_req):
        mock_req.return_value = _make_mock_response({
            'Items': [{'Genres': []}]
        })
        result = get_series_genres_by_ids(['s1'])
        self.assertEqual(result, [[]])

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_passes_correct_fields_param(self, mock_req):
        mock_req.return_value = _make_mock_response({'Items': []})
        get_series_genres_by_ids(['s1'])
        params = mock_req.call_args[1].get('params') or mock_req.call_args[0][2]
        self.assertEqual(params['Fields'], 'Genres')

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_returns_empty_list_when_no_items(self, mock_req):
        mock_req.return_value = _make_mock_response({'Items': []})
        result = get_series_genres_by_ids(['s1'])
        self.assertEqual(result, [])

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_calls_correct_endpoint(self, mock_req):
        mock_req.return_value = _make_mock_response({'Items': []})
        get_series_genres_by_ids(['s1', 's2'])
        url = mock_req.call_args[0][0]
        self.assertEqual(url, 'Items')

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_passes_ids_joined_by_comma(self, mock_req):
        mock_req.return_value = _make_mock_response({'Items': []})
        get_series_genres_by_ids(['s1', 's2'])
        params = mock_req.call_args[1].get('params') or mock_req.call_args[0][2]
        self.assertEqual(params['ids'], 's1,s2')

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_result_is_cached(self, mock_req):
        mock_req.return_value = _make_mock_response({'Items': [{'Genres': ['Drama']}]})
        get_series_genres_by_ids(['s1'])
        get_series_genres_by_ids(['s1'])
        mock_req.assert_called_once()


# ===========================================================================
# get_movie_genres_by_ids
# ===========================================================================

class TestGetMovieGenresByIds(JellyfinTestBase):

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_returns_lowercased_genre_lists(self, mock_req):
        mock_req.return_value = _make_mock_response({
            'Items': [
                {'Genres': ['Horror', 'Thriller']},
                {'Genres': ['Romance']},
            ]
        })
        result = get_movie_genres_by_ids(['m1', 'm2'])
        self.assertEqual(result, [['horror', 'thriller'], ['romance']])

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_returns_empty_inner_list_for_item_with_no_genres(self, mock_req):
        mock_req.return_value = _make_mock_response({
            'Items': [{'Genres': []}]
        })
        result = get_movie_genres_by_ids(['m1'])
        self.assertEqual(result, [[]])

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_returns_empty_list_when_no_items(self, mock_req):
        mock_req.return_value = _make_mock_response({'Items': []})
        result = get_movie_genres_by_ids(['m1'])
        self.assertEqual(result, [])

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_passes_correct_params(self, mock_req):
        mock_req.return_value = _make_mock_response({'Items': []})
        get_movie_genres_by_ids(['m1', 'm2'])
        params = mock_req.call_args[1].get('params') or mock_req.call_args[0][2]
        self.assertEqual(params['Fields'], 'Genres')
        self.assertEqual(params['ids'], 'm1,m2')

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_result_is_cached(self, mock_req):
        mock_req.return_value = _make_mock_response({'Items': [{'Genres': ['Drama']}]})
        get_movie_genres_by_ids(['m1'])
        get_movie_genres_by_ids(['m1'])
        mock_req.assert_called_once()


# ===========================================================================
# get_user_watched_series_ids
# ===========================================================================

class TestGetUserWatchedSeriesIds(JellyfinTestBase):

    def _setup_provider_and_genre_mocks(self, tmdb_ids, genres):
        """Patch both provider-id and genre lookups so Series objects can be built."""
        provider_patch = patch(
            'services.jellyfinAPIService.get_series_provider_ids_by_ids',
            return_value=tmdb_ids
        )
        genre_patch = patch(
            'services.jellyfinAPIService.get_series_genres_by_ids',
            return_value=genres
        )
        return provider_patch, genre_patch

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_returns_series_with_min_episode_count(self, mock_req):
        episodes = [_make_episode('Breaking Bad', 'bb-id')] * 3
        mock_req.return_value = _make_mock_response({'Items': episodes})
        with patch('services.jellyfinAPIService.get_series_provider_ids_by_ids', return_value=['1234']):
            with patch('services.jellyfinAPIService.get_series_genres_by_ids', return_value=[['drama']]):
                result = get_user_watched_series_ids('user-1', min_episode_watch_count=3)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, 'Breaking Bad')

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_excludes_series_below_min_episode_count(self, mock_req):
        # Only 2 episodes watched but minimum is 3
        episodes = [_make_episode('Breaking Bad', 'bb-id')] * 2
        mock_req.return_value = _make_mock_response({'Items': episodes})
        with patch('services.jellyfinAPIService.get_series_provider_ids_by_ids', return_value=[]):
            with patch('services.jellyfinAPIService.get_series_genres_by_ids', return_value=[]):
                result = get_user_watched_series_ids('user-1', min_episode_watch_count=3)
        self.assertEqual(result, [])

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_excludes_series_outside_max_days_window(self, mock_req):
        old_date = (date.today() - timedelta(days=60)).isoformat()
        episodes = [_make_episode('Old Show', 'old-id', last_played_date=old_date)] * 5
        mock_req.return_value = _make_mock_response({'Items': episodes})
        with patch('services.jellyfinAPIService.get_series_provider_ids_by_ids', return_value=[]):
            with patch('services.jellyfinAPIService.get_series_genres_by_ids', return_value=[]):
                result = get_user_watched_series_ids('user-1', max_days=30, min_episode_watch_count=1)
        self.assertEqual(result, [])

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_includes_series_within_max_days_window(self, mock_req):
        recent_date = (date.today() - timedelta(days=5)).isoformat()
        episodes = [_make_episode('Recent Show', 'recent-id', last_played_date=recent_date)] * 2
        mock_req.return_value = _make_mock_response({'Items': episodes})
        with patch('services.jellyfinAPIService.get_series_provider_ids_by_ids', return_value=['555']):
            with patch('services.jellyfinAPIService.get_series_genres_by_ids', return_value=[['sci-fi']]):
                result = get_user_watched_series_ids('user-1', max_days=30, min_episode_watch_count=2)
        self.assertEqual(len(result), 1)

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_skips_episodes_without_user_data(self, mock_req):
        episodes = [
            {'SeriesName': 'Show A', 'SeriesId': 'a-id'},  # no UserData
            _make_episode('Show B', 'b-id'),
            _make_episode('Show B', 'b-id'),
        ]
        mock_req.return_value = _make_mock_response({'Items': episodes})
        with patch('services.jellyfinAPIService.get_series_provider_ids_by_ids', return_value=['999']):
            with patch('services.jellyfinAPIService.get_series_genres_by_ids', return_value=[['drama']]):
                result = get_user_watched_series_ids('user-1', min_episode_watch_count=2)
        ids = [s.id for s in result]
        self.assertNotIn('a-id', ids)
        self.assertIn('b-id', ids)

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_skips_episodes_with_user_data_but_no_last_played_date(self, mock_req):
        # Episode has UserData but no LastPlayedDate -> skipped (not counted).
        episodes = [
            {'SeriesName': 'No Date', 'SeriesId': 'nodate-id', 'UserData': {'PlayCount': 1}},
            {'SeriesName': 'No Date', 'SeriesId': 'nodate-id', 'UserData': {'PlayCount': 1}},
            _make_episode('Has Date', 'hasdate-id'),
        ]
        mock_req.return_value = _make_mock_response({'Items': episodes})
        with patch('services.jellyfinAPIService.get_series_provider_ids_by_ids', return_value=['123']):
            with patch('services.jellyfinAPIService.get_series_genres_by_ids', return_value=[['drama']]):
                result = get_user_watched_series_ids('user-1', min_episode_watch_count=1)
        ids = [s.id for s in result]
        self.assertNotIn('nodate-id', ids)
        self.assertIn('hasdate-id', ids)

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_excludes_series_with_no_tmdb_id(self, mock_req):
        episodes = [_make_episode('No TMDB', 'no-tmdb-id')] * 3
        mock_req.return_value = _make_mock_response({'Items': episodes})
        # None means no TMDB ID found for this series
        with patch('services.jellyfinAPIService.get_series_provider_ids_by_ids', return_value=[None]):
            with patch('services.jellyfinAPIService.get_series_genres_by_ids', return_value=[[]]):
                result = get_user_watched_series_ids('user-1', min_episode_watch_count=1)
        self.assertEqual(result, [])

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_calls_correct_endpoint(self, mock_req):
        mock_req.return_value = _make_mock_response({'Items': []})
        with patch('services.jellyfinAPIService.get_series_provider_ids_by_ids', return_value=[]):
            with patch('services.jellyfinAPIService.get_series_genres_by_ids', return_value=[]):
                get_user_watched_series_ids('user-42', min_episode_watch_count=1)
        url = mock_req.call_args[0][0]
        self.assertEqual(url, 'Users/user-42/Items')

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_no_max_days_includes_all_episodes(self, mock_req):
        old_date = (date.today() - timedelta(days=365)).isoformat()
        episodes = [_make_episode('Old Show', 'old-id', last_played_date=old_date)] * 3
        mock_req.return_value = _make_mock_response({'Items': episodes})
        with patch('services.jellyfinAPIService.get_series_provider_ids_by_ids', return_value=['111']):
            with patch('services.jellyfinAPIService.get_series_genres_by_ids', return_value=[['drama']]):
                result = get_user_watched_series_ids('user-1', max_days=None, min_episode_watch_count=3)
        self.assertEqual(len(result), 1)


# ===========================================================================
# get_user_fully_watched_movies
# ===========================================================================

class TestGetUserFullyWatchedMovies(JellyfinTestBase):

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_returns_watched_movies(self, mock_req):
        movies = [_make_movie_item('Film A'), _make_movie_item('Film B')]
        mock_req.return_value = _make_mock_response({'Items': movies})
        result = get_user_fully_watched_movies('user-1')
        self.assertEqual(len(result), 2)

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_calls_correct_endpoint(self, mock_req):
        mock_req.return_value = _make_mock_response({'Items': []})
        get_user_fully_watched_movies('user-5')
        url = mock_req.call_args[0][0]
        self.assertEqual(url, 'Users/user-5/Items')

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_passes_correct_params(self, mock_req):
        mock_req.return_value = _make_mock_response({'Items': []})
        get_user_fully_watched_movies('user-1')
        params = mock_req.call_args[1].get('params') or mock_req.call_args[0][2]
        self.assertEqual(params['Filters'], 'IsPlayed')
        self.assertEqual(params['IncludeItemTypes'], 'Movie')


# ===========================================================================
# get_user_in_progress_movies
# ===========================================================================

class TestGetUserInProgressMovies(JellyfinTestBase):

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_returns_all_when_no_min_progress(self, mock_req):
        movies = [
            _make_movie_item('Film A', played_percentage=10.0),
            _make_movie_item('Film B', played_percentage=80.0),
        ]
        mock_req.return_value = _make_mock_response({'Items': movies})
        result = get_user_in_progress_movies('user-1')
        self.assertEqual(len(result), 2)

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_filters_below_min_progress_percent(self, mock_req):
        movies = [
            _make_movie_item('Film A', played_percentage=20.0),
            _make_movie_item('Film B', played_percentage=75.0),
        ]
        mock_req.return_value = _make_mock_response({'Items': movies})
        result = get_user_in_progress_movies('user-1', min_progress_percent=50)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['Name'], 'Film B')

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_skips_items_without_user_data(self, mock_req):
        movies = [
            {'Name': 'No UserData', 'Id': 'x'},
            _make_movie_item('Film B', played_percentage=80.0),
        ]
        mock_req.return_value = _make_mock_response({'Items': movies})
        result = get_user_in_progress_movies('user-1', min_progress_percent=50)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['Name'], 'Film B')

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_skips_falsy_items_when_filtering_by_progress(self, mock_req):
        # A None/empty entry in the list must be skipped without error when a
        # minimum progress threshold triggers the filtering branch.
        movies = [
            None,
            {},
            _make_movie_item('Film B', played_percentage=80.0),
        ]
        mock_req.return_value = _make_mock_response({'Items': movies})
        result = get_user_in_progress_movies('user-1', min_progress_percent=50)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['Name'], 'Film B')

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_calls_correct_endpoint_with_resumable_filter(self, mock_req):
        mock_req.return_value = _make_mock_response({'Items': []})
        get_user_in_progress_movies('user-3')
        url = mock_req.call_args[0][0]
        self.assertEqual(url, 'Users/user-3/Items')
        params = mock_req.call_args[1].get('params') or mock_req.call_args[0][2]
        self.assertEqual(params['Filters'], 'IsResumable')


# ===========================================================================
# get_all_user_movies
# ===========================================================================

class TestGetAllUserMovies(JellyfinTestBase):

    @patch('services.jellyfinAPIService.get_movies_provider_ids_by_ids')
    @patch('services.jellyfinAPIService.get_movie_genres_by_ids')
    @patch('services.jellyfinAPIService.get_user_in_progress_movies')
    @patch('services.jellyfinAPIService.get_user_fully_watched_movies')
    def test_combines_watched_and_in_progress(self, mock_watched, mock_in_progress, mock_genres, mock_provider_ids):
        mock_watched.return_value = [_make_movie_item('Film A', item_id='a' * 32, tmdb_id='1')]
        mock_in_progress.return_value = [_make_movie_item('Film B', item_id='b' * 32, tmdb_id='2')]
        mock_genres.return_value = [['action'], ['drama']]
        mock_provider_ids.return_value = ['1', '2']

        result = get_all_user_movies('user-1')
        self.assertEqual(len(result), 2)

    @patch('services.jellyfinAPIService.get_movies_provider_ids_by_ids')
    @patch('services.jellyfinAPIService.get_movie_genres_by_ids')
    @patch('services.jellyfinAPIService.get_user_in_progress_movies')
    @patch('services.jellyfinAPIService.get_user_fully_watched_movies')
    def test_excludes_movies_outside_max_days(self, mock_watched, mock_in_progress, mock_genres, mock_provider_ids):
        old_date = (date.today() - timedelta(days=90)).isoformat()
        mock_watched.return_value = [_make_movie_item('Old Film', item_id='c' * 32, last_played_date=old_date)]
        mock_in_progress.return_value = []
        mock_genres.return_value = []
        mock_provider_ids.return_value = []

        result = get_all_user_movies('user-1', max_days=30)
        self.assertEqual(result, [])

    @patch('services.jellyfinAPIService.get_movies_provider_ids_by_ids')
    @patch('services.jellyfinAPIService.get_movie_genres_by_ids')
    @patch('services.jellyfinAPIService.get_user_in_progress_movies')
    @patch('services.jellyfinAPIService.get_user_fully_watched_movies')
    def test_excludes_movies_without_tmdb_id(self, mock_watched, mock_in_progress, mock_genres, mock_provider_ids):
        mock_watched.return_value = [_make_movie_item('No TMDB', item_id='d' * 32)]
        mock_in_progress.return_value = []
        mock_genres.return_value = [[]]
        mock_provider_ids.return_value = [None]  # No TMDB ID

        result = get_all_user_movies('user-1')
        self.assertEqual(result, [])

    @patch('services.jellyfinAPIService.get_movies_provider_ids_by_ids')
    @patch('services.jellyfinAPIService.get_movie_genres_by_ids')
    @patch('services.jellyfinAPIService.get_user_in_progress_movies')
    @patch('services.jellyfinAPIService.get_user_fully_watched_movies')
    def test_skips_items_without_user_data(self, mock_watched, mock_in_progress, mock_genres, mock_provider_ids):
        mock_watched.return_value = [{'Name': 'No UserData', 'Id': 'e' * 32}]
        mock_in_progress.return_value = []
        mock_genres.return_value = []
        mock_provider_ids.return_value = []

        result = get_all_user_movies('user-1')
        self.assertEqual(result, [])

    @patch('services.jellyfinAPIService.get_movies_provider_ids_by_ids')
    @patch('services.jellyfinAPIService.get_movie_genres_by_ids')
    @patch('services.jellyfinAPIService.get_user_in_progress_movies')
    @patch('services.jellyfinAPIService.get_user_fully_watched_movies')
    def test_skips_items_with_user_data_but_no_last_played_date(self, mock_watched, mock_in_progress, mock_genres, mock_provider_ids):
        # UserData present but LastPlayedDate missing -> movie is skipped.
        no_date_movie = {'Name': 'No Date', 'Id': 'f' * 32, 'ProviderIds': {'Tmdb': '1'}, 'UserData': {'PlayCount': 1}}
        good_movie = _make_movie_item('Film B', item_id='b' * 32, tmdb_id='2')
        mock_watched.return_value = [no_date_movie, good_movie]
        mock_in_progress.return_value = []
        mock_genres.return_value = [['drama']]
        mock_provider_ids.return_value = ['2']

        result = get_all_user_movies('user-1')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, 'Film B')


# ===========================================================================
# get_all_available_movies
# ===========================================================================

class TestSelectLibraryScopingUser(JellyfinTestBase):

    def _user(self, uid, admin=False, disabled=False, max_rating=None):
        return {"Id": uid, "Policy": {
            "IsAdministrator": admin, "IsDisabled": disabled, "MaxParentalRating": max_rating,
        }}

    @patch('services.jellyfinAPIService.get_users')
    def test_prefers_enabled_uncapped_admin(self, mock_users):
        mock_users.return_value = [
            self._user("capped", max_rating=10),
            self._user("plain-user"),
            self._user("the-admin", admin=True),
        ]
        self.assertEqual(_select_library_scoping_user(), "the-admin")

    @patch('services.jellyfinAPIService.get_users')
    def test_falls_back_to_any_uncapped_user_when_no_admin(self, mock_users):
        mock_users.return_value = [
            self._user("capped", max_rating=7),
            self._user("open-user"),
        ]
        self.assertEqual(_select_library_scoping_user(), "open-user")

    @patch('services.jellyfinAPIService.get_users')
    def test_skips_disabled_admin(self, mock_users):
        mock_users.return_value = [
            self._user("dead-admin", admin=True, disabled=True),
            self._user("live-user"),
        ]
        self.assertEqual(_select_library_scoping_user(), "live-user")

    @patch('services.jellyfinAPIService.get_users')
    def test_falls_back_to_first_user_when_all_capped(self, mock_users):
        mock_users.return_value = [
            self._user("first-capped", max_rating=10),
            self._user("second-capped", max_rating=7),
        ]
        self.assertEqual(_select_library_scoping_user(), "first-capped")

    @patch('services.jellyfinAPIService.get_users', return_value=[])
    def test_returns_none_when_no_users(self, mock_users):
        self.assertIsNone(_select_library_scoping_user())


class TestGetAllAvailableMovies(JellyfinTestBase):

    def setUp(self):
        super().setUp()
        # No-user calls resolve the enumeration identity via get_users(); stub it
        # so these tests exercise extraction/paging without a real user list.
        self._users_patch = patch(
            'services.jellyfinAPIService.get_users', return_value=[{'Id': 'first-user'}]
        )
        self._users_patch.start()

    def tearDown(self):
        self._users_patch.stop()

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_returns_tmdb_ids_as_ints(self, mock_req):
        mock_req.return_value = _make_mock_response({
            'Items': [_make_library_item('100'), _make_library_item('200')]
        })
        with patch.dict(os.environ, {'MOVIE_LIBRARY_IDS': ''}):
            result = get_all_available_movies()
        self.assertEqual(result, [100, 200])

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_skips_items_without_tmdb_id(self, mock_req):
        mock_req.return_value = _make_mock_response({
            'Items': [{'ProviderIds': {}}, _make_library_item('300')]
        })
        with patch.dict(os.environ, {'MOVIE_LIBRARY_IDS': ''}):
            result = get_all_available_movies()
        self.assertEqual(result, [300])

    @patch('services.jellyfinAPIService.get_users', return_value=[{'Id': 'first-user'}])
    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_falls_back_to_first_user_without_user_id(self, mock_req, mock_users):
        # The bare /Items endpoint under-reports the library, so a no-user call
        # must enumerate via the first Jellyfin user instead.
        mock_req.return_value = _make_mock_response({'Items': []})
        with patch.dict(os.environ, {'MOVIE_LIBRARY_IDS': ''}):
            get_all_available_movies()
        url = mock_req.call_args[0][0]
        self.assertEqual(url, 'Users/first-user/Items')

    @patch('services.jellyfinAPIService.get_users', return_value=[])
    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_uses_items_endpoint_when_no_users_exist(self, mock_req, mock_users):
        mock_req.return_value = _make_mock_response({'Items': []})
        with patch.dict(os.environ, {'MOVIE_LIBRARY_IDS': ''}):
            get_all_available_movies()
        url = mock_req.call_args[0][0]
        self.assertEqual(url, 'Items')

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_always_enumerates_via_scoping_user(self, mock_req):
        # Availability is user-agnostic: it always enumerates via the resolved
        # scoping user (stubbed in setUp as 'first-user'), never a target user.
        mock_req.return_value = _make_mock_response({'Items': []})
        with patch.dict(os.environ, {'MOVIE_LIBRARY_IDS': ''}):
            get_all_available_movies()
        url = mock_req.call_args[0][0]
        self.assertEqual(url, 'Users/first-user/Items')

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_queries_each_library_id_separately(self, mock_req):
        mock_req.return_value = _make_mock_response({'Items': []})
        with patch.dict(os.environ, {'MOVIE_LIBRARY_IDS': 'lib1,lib2'}):
            get_all_available_movies()
        self.assertEqual(mock_req.call_count, 2)
        parent_ids = [
            (mock_req.call_args_list[i][1].get('params') or mock_req.call_args_list[i][0][2]).get('ParentId')
            for i in range(2)
        ]
        self.assertIn('lib1', parent_ids)
        self.assertIn('lib2', parent_ids)

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_result_is_cached(self, mock_req):
        mock_req.return_value = _make_mock_response({'Items': [_make_library_item('1')]})
        with patch.dict(os.environ, {'MOVIE_LIBRARY_IDS': ''}):
            get_all_available_movies()
            get_all_available_movies()
        mock_req.assert_called_once()

    @patch('services.jellyfinAPIService.tmdb_api_service.get_tmdb_id_from_external_id')
    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_resolves_imdb_id_when_tmdb_missing(self, mock_req, mock_resolve):
        # Item carries only an IMDb id; it must be resolved to a TMDB id so it
        # still lands in the exclusion set.
        mock_req.return_value = _make_mock_response({
            'Items': [{'ProviderIds': {'Imdb': 'tt0133093'}}, _make_library_item('200')]
        })
        mock_resolve.return_value = 603
        with patch.dict(os.environ, {'MOVIE_LIBRARY_IDS': ''}):
            result = get_all_available_movies()
        self.assertEqual(sorted(result), [200, 603])
        mock_resolve.assert_called_once_with('Imdb', 'tt0133093', 'movie')

    @patch('services.jellyfinAPIService.tmdb_api_service.get_tmdb_id_from_external_id')
    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_prefers_direct_tmdb_id_over_resolution(self, mock_req, mock_resolve):
        mock_req.return_value = _make_mock_response({
            'Items': [{'ProviderIds': {'Tmdb': '42', 'Imdb': 'tt1'}}]
        })
        with patch.dict(os.environ, {'MOVIE_LIBRARY_IDS': ''}):
            result = get_all_available_movies()
        self.assertEqual(result, [42])
        mock_resolve.assert_not_called()

    @patch('services.jellyfinAPIService.tmdb_api_service.get_tmdb_id_from_external_id')
    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_drops_item_when_resolution_fails(self, mock_req, mock_resolve):
        mock_req.return_value = _make_mock_response({
            'Items': [{'ProviderIds': {'Imdb': 'tt0000000'}}]
        })
        mock_resolve.return_value = None
        with patch.dict(os.environ, {'MOVIE_LIBRARY_IDS': ''}):
            result = get_all_available_movies()
        self.assertEqual(result, [])


# ===========================================================================
# get_all_available_series
# ===========================================================================

class TestGetAllAvailableSeries(JellyfinTestBase):

    def setUp(self):
        super().setUp()
        self._users_patch = patch(
            'services.jellyfinAPIService.get_users', return_value=[{'Id': 'first-user'}]
        )
        self._users_patch.start()

    def tearDown(self):
        self._users_patch.stop()

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_returns_tmdb_ids_as_ints(self, mock_req):
        mock_req.return_value = _make_mock_response({
            'Items': [_make_library_item('400'), _make_library_item('500')]
        })
        with patch.dict(os.environ, {'SERIES_LIBRARY_IDS': ''}):
            result = get_all_available_series()
        self.assertEqual(result, [400, 500])

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_skips_items_without_tmdb_id(self, mock_req):
        mock_req.return_value = _make_mock_response({
            'Items': [{'ProviderIds': {}}, _make_library_item('600')]
        })
        with patch.dict(os.environ, {'SERIES_LIBRARY_IDS': ''}):
            result = get_all_available_series()
        self.assertEqual(result, [600])

    @patch('services.jellyfinAPIService.get_users', return_value=[{'Id': 'first-user'}])
    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_falls_back_to_first_user_without_user_id(self, mock_req, mock_users):
        mock_req.return_value = _make_mock_response({'Items': []})
        with patch.dict(os.environ, {'SERIES_LIBRARY_IDS': ''}):
            get_all_available_series()
        url = mock_req.call_args[0][0]
        self.assertEqual(url, 'Users/first-user/Items')

    @patch('services.jellyfinAPIService.get_users', return_value=[])
    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_uses_items_endpoint_when_no_users_exist(self, mock_req, mock_users):
        mock_req.return_value = _make_mock_response({'Items': []})
        with patch.dict(os.environ, {'SERIES_LIBRARY_IDS': ''}):
            get_all_available_series()
        url = mock_req.call_args[0][0]
        self.assertEqual(url, 'Items')

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_always_enumerates_via_scoping_user(self, mock_req):
        mock_req.return_value = _make_mock_response({'Items': []})
        with patch.dict(os.environ, {'SERIES_LIBRARY_IDS': ''}):
            get_all_available_series()
        url = mock_req.call_args[0][0]
        self.assertEqual(url, 'Users/first-user/Items')

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_queries_each_library_id_separately(self, mock_req):
        mock_req.return_value = _make_mock_response({'Items': []})
        with patch.dict(os.environ, {'SERIES_LIBRARY_IDS': 'slib1,slib2,slib3'}):
            get_all_available_series()
        self.assertEqual(mock_req.call_count, 3)

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_result_is_cached(self, mock_req):
        mock_req.return_value = _make_mock_response({'Items': [_make_library_item('1')]})
        with patch.dict(os.environ, {'SERIES_LIBRARY_IDS': ''}):
            get_all_available_series()
            get_all_available_series()
        mock_req.assert_called_once()

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_passes_series_include_type(self, mock_req):
        mock_req.return_value = _make_mock_response({'Items': []})
        with patch.dict(os.environ, {'SERIES_LIBRARY_IDS': ''}):
            get_all_available_series()
        params = mock_req.call_args[1].get('params') or mock_req.call_args[0][2]
        self.assertEqual(params['IncludeItemTypes'], 'Series')

    @patch('services.jellyfinAPIService.tmdb_api_service.get_tmdb_id_from_external_id')
    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_resolves_tvdb_id_when_tmdb_missing(self, mock_req, mock_resolve):
        # Common for TV: Jellyfin tags only a TVDB id. It must resolve to TMDB.
        mock_req.return_value = _make_mock_response({
            'Items': [{'ProviderIds': {'Tvdb': '121361'}}, _make_library_item('500')]
        })
        mock_resolve.return_value = 1399
        with patch.dict(os.environ, {'SERIES_LIBRARY_IDS': ''}):
            result = get_all_available_series()
        self.assertEqual(sorted(result), [500, 1399])
        mock_resolve.assert_called_once_with('Tvdb', '121361', 'tv')


# ===========================================================================
# delete_item_by_id
# ===========================================================================

class TestDeleteItemById(JellyfinTestBase):

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_calls_delete_with_formatted_uuid(self, mock_req):
        mock_req.return_value = MagicMock()
        raw_id = 'a1b2c3d4e5f6789012345678abcdef12'  # 32 chars, no dashes
        get_item_by_id = delete_item_by_id(raw_id)
        url = mock_req.call_args[0][0]
        self.assertIn('Items/', url)
        self.assertEqual(mock_req.call_args[1].get('method') or mock_req.call_args[0][1], 'DELETE')

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_returns_none_for_empty_id(self, mock_req):
        result = delete_item_by_id('')
        mock_req.assert_not_called()
        self.assertIsNone(result)

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_returns_none_for_none_id(self, mock_req):
        result = delete_item_by_id(None)
        mock_req.assert_not_called()
        self.assertIsNone(result)

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_raises_for_invalid_length_id(self, mock_req):
        with self.assertRaises(Exception):
            delete_item_by_id('tooshort')


# ===========================================================================
# get_item_path
# ===========================================================================

class TestGetItemPath(JellyfinTestBase):

    def test_prefers_media_source_path(self):
        item = {
            'Path': '/top/level.mkv',
            'MediaSources': [{'Path': '/media/source.mkv'}],
        }
        self.assertEqual(get_item_path(item), '/media/source.mkv')

    def test_falls_back_to_top_level_path(self):
        item = {'Path': '/top/level.mkv', 'MediaSources': []}
        self.assertEqual(get_item_path(item), '/top/level.mkv')

    def test_falls_back_when_media_source_has_no_path(self):
        item = {'Path': '/top/level.mkv', 'MediaSources': [{'Path': None}]}
        self.assertEqual(get_item_path(item), '/top/level.mkv')

    def test_returns_none_when_nothing_present(self):
        self.assertIsNone(get_item_path({}))

    def test_returns_none_for_falsy_item(self):
        self.assertIsNone(get_item_path(None))


# ===========================================================================
# get_items_by_tmdb_ids
# ===========================================================================

class TestGetItemsByTmdbIds(JellyfinTestBase):

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_filters_to_requested_tmdb_ids(self, mock_req):
        items = [
            {'Name': 'A', 'ProviderIds': {'Tmdb': '100'}},
            {'Name': 'B', 'ProviderIds': {'Tmdb': '200'}},
            {'Name': 'C', 'ProviderIds': {'Tmdb': '300'}},
        ]
        mock_req.return_value = _make_mock_response({'Items': items})
        result = get_items_by_tmdb_ids([100, 300], 'Movie')
        names = [item['Name'] for item in result]
        self.assertEqual(names, ['A', 'C'])

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_matches_int_ids_against_string_provider_ids(self, mock_req):
        items = [{'Name': 'A', 'ProviderIds': {'Tmdb': '100'}}]
        mock_req.return_value = _make_mock_response({'Items': items})
        result = get_items_by_tmdb_ids([100], 'Series')
        self.assertEqual(len(result), 1)

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_returns_empty_for_no_ids_without_calling_api(self, mock_req):
        self.assertEqual(get_items_by_tmdb_ids([], 'Movie'), [])
        mock_req.assert_not_called()

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_requests_correct_item_type_and_fields(self, mock_req):
        mock_req.return_value = _make_mock_response({'Items': []})
        get_items_by_tmdb_ids([1], 'Series')
        params = mock_req.call_args[1].get('params') or mock_req.call_args[0][2]
        self.assertEqual(params['IncludeItemTypes'], 'Series')
        self.assertIn('ProviderIds', params['Fields'])
        self.assertIn('MediaSources', params['Fields'])

    def test_rejects_invalid_item_type(self):
        with self.assertRaises(Exception) as ctx:
            get_items_by_tmdb_ids([1], 'Album')
        self.assertIn("['Movie', 'Series']", str(ctx.exception))


# ===========================================================================
# get_series_episode_paths
# ===========================================================================

class TestGetSeriesEpisodePaths(JellyfinTestBase):

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_returns_season_episode_path_name(self, mock_req):
        episodes = [
            {'ParentIndexNumber': 1, 'IndexNumber': 1, 'Path': '/s1e1.mkv', 'Name': 'Pilot'},
            {'ParentIndexNumber': 1, 'IndexNumber': 2,
             'MediaSources': [{'Path': '/s1e2.mkv'}], 'Name': 'Ep2'},
        ]
        mock_req.return_value = _make_mock_response({'Items': episodes})
        result = get_series_episode_paths('series-1')
        self.assertEqual(result[0], {'season': 1, 'episode': 1, 'path': '/s1e1.mkv', 'name': 'Pilot'})
        self.assertEqual(result[1]['path'], '/s1e2.mkv')

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_skips_episodes_without_path(self, mock_req):
        episodes = [
            {'ParentIndexNumber': 1, 'IndexNumber': 1, 'Name': 'No path'},
            {'ParentIndexNumber': 1, 'IndexNumber': 2, 'Path': '/s1e2.mkv', 'Name': 'Has path'},
        ]
        mock_req.return_value = _make_mock_response({'Items': episodes})
        result = get_series_episode_paths('series-1')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['episode'], 2)

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_hits_shows_episodes_endpoint(self, mock_req):
        mock_req.return_value = _make_mock_response({'Items': []})
        get_series_episode_paths('series-xyz')
        url = mock_req.call_args[0][0]
        self.assertEqual(url, 'Shows/series-xyz/Episodes')

    def test_returns_empty_for_falsy_id(self):
        self.assertEqual(get_series_episode_paths(''), [])


# ===========================================================================
# Library management
# ===========================================================================

class TestVirtualFolders(JellyfinTestBase):

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_get_virtual_folders_returns_json(self, mock_req):
        folders = [{'Name': 'Movies', 'ItemId': '1'}]
        mock_req.return_value = _make_mock_response(folders)
        self.assertEqual(get_virtual_folders(), folders)

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_get_virtual_folder_by_name_match(self, mock_req):
        folders = [{'Name': 'Movies', 'ItemId': '1'}, {'Name': 'Requests (bob)', 'ItemId': '2'}]
        mock_req.return_value = _make_mock_response(folders)
        self.assertEqual(get_virtual_folder_by_name('Requests (bob)')['ItemId'], '2')

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_get_virtual_folder_by_name_no_match(self, mock_req):
        mock_req.return_value = _make_mock_response([{'Name': 'Movies', 'ItemId': '1'}])
        self.assertIsNone(get_virtual_folder_by_name('Requests (nobody)'))

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_create_library_params_and_body(self, mock_req):
        mock_req.return_value = MagicMock()
        create_library('Requests (bob)', '/recs/bob/requests')
        url = mock_req.call_args[0][0]
        method = mock_req.call_args[1].get('method') or mock_req.call_args[0][1]
        params = mock_req.call_args[1].get('params')
        body = mock_req.call_args[1].get('body')
        self.assertEqual(url, 'Library/VirtualFolders')
        self.assertEqual(method, 'POST')
        self.assertEqual(params['name'], 'Requests (bob)')
        self.assertEqual(params['collectionType'], 'mixed')
        self.assertEqual(params['paths'], ['/recs/bob/requests'])
        # Boolean query params must be lowercase strings for Jellyfin.
        self.assertEqual(params['refreshLibrary'], 'true')
        self.assertEqual(body['LibraryOptions'], DEFAULT_LIBRARY_OPTIONS)

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_refresh_libraries_posts(self, mock_req):
        mock_req.return_value = MagicMock()
        refresh_libraries()
        url = mock_req.call_args[0][0]
        method = mock_req.call_args[1].get('method') or mock_req.call_args[0][1]
        self.assertEqual(url, 'Library/Refresh')
        self.assertEqual(method, 'POST')

    def test_default_library_options_values(self):
        self.assertTrue(DEFAULT_LIBRARY_OPTIONS['EnableRealtimeMonitor'])
        self.assertFalse(DEFAULT_LIBRARY_OPTIONS['EnableTrickplayImageExtraction'])
        self.assertFalse(DEFAULT_LIBRARY_OPTIONS['EnableChapterImageExtraction'])
        self.assertEqual(DEFAULT_LIBRARY_OPTIONS['SubtitleDownloadLanguages'], [])


# ===========================================================================
# add_library_to_user  (policy-merge safety)
# ===========================================================================

class TestAddLibraryToUser(JellyfinTestBase):

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_appends_to_existing_enabled_folders(self, mock_req):
        # First call: GET user (policy). Second call: POST policy.
        mock_req.side_effect = [
            _make_mock_response({'Policy': {'EnableAllFolders': False, 'EnabledFolders': ['lib-1']}}),
            MagicMock(),
        ]
        add_library_to_user('user-1', 'lib-2')
        post_call = mock_req.call_args_list[1]
        posted_policy = post_call[1].get('body') or post_call[0][3]
        self.assertEqual(posted_policy['EnabledFolders'], ['lib-1', 'lib-2'])
        # Must not have touched the all-folders flag.
        self.assertFalse(posted_policy['EnableAllFolders'])

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_does_nothing_when_enable_all_folders(self, mock_req):
        mock_req.return_value = _make_mock_response({'Policy': {'EnableAllFolders': True, 'EnabledFolders': []}})
        add_library_to_user('user-1', 'lib-2')
        # Only the GET happened; no POST to change policy.
        self.assertEqual(mock_req.call_count, 1)

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_does_nothing_when_already_enabled(self, mock_req):
        mock_req.return_value = _make_mock_response({'Policy': {'EnableAllFolders': False, 'EnabledFolders': ['lib-2']}})
        add_library_to_user('user-1', 'lib-2')
        self.assertEqual(mock_req.call_count, 1)

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_handles_missing_enabled_folders_key(self, mock_req):
        mock_req.side_effect = [
            _make_mock_response({'Policy': {'EnableAllFolders': False}}),
            MagicMock(),
        ]
        add_library_to_user('user-1', 'lib-2')
        posted_policy = mock_req.call_args_list[1][1].get('body') or mock_req.call_args_list[1][0][3]
        self.assertEqual(posted_policy['EnabledFolders'], ['lib-2'])

    def test_raises_when_args_missing(self):
        with self.assertRaises(Exception):
            add_library_to_user('', 'lib')
        with self.assertRaises(Exception):
            add_library_to_user('user', '')

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_posts_to_user_policy_endpoint(self, mock_req):
        mock_req.side_effect = [
            _make_mock_response({'Policy': {'EnableAllFolders': False, 'EnabledFolders': []}}),
            MagicMock(),
        ]
        add_library_to_user('user-9', 'lib-x')
        post_call = mock_req.call_args_list[1]
        url = post_call[0][0]
        self.assertEqual(url, 'Users/user-9/Policy')


# ===========================================================================
# Collections
# ===========================================================================

class TestGetCollections(JellyfinTestBase):

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_returns_boxset_items(self, mock_req):
        items = [{'Id': 'c1', 'Name': 'Requests - Alice'}]
        mock_req.return_value = _make_mock_response({'Items': items})
        result = get_collections()
        self.assertEqual(result, items)

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_queries_boxset_recursively(self, mock_req):
        mock_req.return_value = _make_mock_response({'Items': []})
        get_collections()
        params = mock_req.call_args.kwargs['params']
        self.assertEqual(params['IncludeItemTypes'], 'BoxSet')
        self.assertTrue(params['Recursive'])


class TestGetCollectionByName(JellyfinTestBase):

    @patch('services.jellyfinAPIService.get_collections')
    def test_returns_exact_name_match(self, mock_get):
        mock_get.return_value = [
            {'Id': 'c1', 'Name': 'Requests - Alice'},
            {'Id': 'c2', 'Name': 'Requests - Bob'},
        ]
        result = get_collection_by_name('Requests - Bob')
        self.assertEqual(result['Id'], 'c2')

    @patch('services.jellyfinAPIService.get_collections')
    def test_returns_none_when_absent(self, mock_get):
        mock_get.return_value = [{'Id': 'c1', 'Name': 'Requests - Alice'}]
        self.assertIsNone(get_collection_by_name('Requests - Carol'))


class TestGetCollectionItems(JellyfinTestBase):

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_returns_member_items(self, mock_req):
        items = [{'Id': 'm1'}, {'Id': 'm2'}]
        mock_req.return_value = _make_mock_response({'Items': items})
        result = get_collection_items('c1')
        self.assertEqual(result, items)
        params = mock_req.call_args.kwargs['params']
        self.assertEqual(params['ParentId'], 'c1')

    def test_empty_id_returns_empty_without_request(self):
        self.assertEqual(get_collection_items(''), [])


class TestCreateCollection(JellyfinTestBase):

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_returns_new_id_and_seeds_items(self, mock_req):
        mock_req.return_value = _make_mock_response({'Id': 'new-c'})
        result = create_collection('Requests - Alice', ['m1', 'm2'])
        self.assertEqual(result, 'new-c')
        args, kwargs = mock_req.call_args
        self.assertEqual(args[0], 'Collections')
        self.assertEqual(kwargs['method'], 'POST')
        self.assertEqual(kwargs['params']['name'], 'Requests - Alice')
        self.assertEqual(kwargs['params']['ids'], 'm1,m2')

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_omits_ids_when_none(self, mock_req):
        mock_req.return_value = _make_mock_response({'Id': 'new-c'})
        create_collection('Requests - Alice')
        self.assertNotIn('ids', mock_req.call_args.kwargs['params'])

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_seed_ids_are_chunked(self, mock_req):
        mock_req.return_value = _make_mock_response({'Id': 'new-c'})
        # Remainder kept within a single batch so the seed-then-add flow produces
        # exactly two calls; cross-batch chunking of the remainder is covered by
        # TestAddItemsToCollection.
        ids = [f'm{i}' for i in range(COLLECTION_ITEMS_BATCH_SIZE + 5)]
        create_collection('Requests - Alice', ids)

        calls = mock_req.call_args_list
        # First call creates the collection seeded with the first batch.
        create_call = calls[0]
        self.assertEqual(create_call.args[0], 'Collections')
        self.assertEqual(
            create_call.kwargs['params']['ids'],
            ','.join(ids[:COLLECTION_ITEMS_BATCH_SIZE]),
        )
        # Remainder is added to the new collection in a follow-up batch.
        add_call = calls[1]
        self.assertEqual(add_call.args[0], 'Collections/new-c/Items')
        self.assertEqual(
            add_call.kwargs['params']['ids'],
            ','.join(ids[COLLECTION_ITEMS_BATCH_SIZE:]),
        )
        self.assertEqual(len(calls), 2)


class TestAddItemsToCollection(JellyfinTestBase):

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_posts_csv_ids(self, mock_req):
        mock_req.return_value = MagicMock()
        add_items_to_collection('c1', ['m1', 'm2'])
        args, kwargs = mock_req.call_args
        self.assertEqual(args[0], 'Collections/c1/Items')
        self.assertEqual(kwargs['method'], 'POST')
        self.assertEqual(kwargs['params']['ids'], 'm1,m2')

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_ids_are_chunked_across_requests(self, mock_req):
        mock_req.return_value = MagicMock()
        ids = [f'm{i}' for i in range(COLLECTION_ITEMS_BATCH_SIZE * 2 + 1)]
        add_items_to_collection('c1', ids)

        self.assertEqual(mock_req.call_count, 3)
        sent = [c.kwargs['params']['ids'].split(',') for c in mock_req.call_args_list]
        self.assertEqual([len(batch) for batch in sent], [COLLECTION_ITEMS_BATCH_SIZE, COLLECTION_ITEMS_BATCH_SIZE, 1])
        # Every id is sent exactly once, in order.
        self.assertEqual([i for batch in sent for i in batch], ids)

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_empty_list_is_noop(self, mock_req):
        add_items_to_collection('c1', [])
        mock_req.assert_not_called()


class TestRemoveItemsFromCollection(JellyfinTestBase):

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_deletes_csv_ids(self, mock_req):
        mock_req.return_value = MagicMock()
        remove_items_from_collection('c1', ['m1', 'm2'])
        args, kwargs = mock_req.call_args
        self.assertEqual(args[0], 'Collections/c1/Items')
        self.assertEqual(kwargs['method'], 'DELETE')
        self.assertEqual(kwargs['params']['ids'], 'm1,m2')

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_ids_are_chunked_across_requests(self, mock_req):
        mock_req.return_value = MagicMock()
        ids = [f'm{i}' for i in range(COLLECTION_ITEMS_BATCH_SIZE + 1)]
        remove_items_from_collection('c1', ids)

        self.assertEqual(mock_req.call_count, 2)
        for c in mock_req.call_args_list:
            self.assertEqual(c.kwargs['method'], 'DELETE')
        sent = [c.kwargs['params']['ids'].split(',') for c in mock_req.call_args_list]
        self.assertEqual([len(batch) for batch in sent], [COLLECTION_ITEMS_BATCH_SIZE, 1])

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_empty_list_is_noop(self, mock_req):
        remove_items_from_collection('c1', [])
        mock_req.assert_not_called()


if __name__ == '__main__':
    unittest.main()

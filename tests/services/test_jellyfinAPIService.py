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
    _make_authenticated_jellyfin_api_request,
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

class TestGetAllAvailableMovies(JellyfinTestBase):

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

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_uses_items_endpoint_without_user_id(self, mock_req):
        mock_req.return_value = _make_mock_response({'Items': []})
        with patch.dict(os.environ, {'MOVIE_LIBRARY_IDS': ''}):
            get_all_available_movies()
        url = mock_req.call_args[0][0]
        self.assertEqual(url, 'Items')

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_uses_user_items_endpoint_with_user_id(self, mock_req):
        mock_req.return_value = _make_mock_response({'Items': []})
        with patch.dict(os.environ, {'MOVIE_LIBRARY_IDS': ''}):
            get_all_available_movies(user_id='user-99')
        url = mock_req.call_args[0][0]
        self.assertEqual(url, 'Users/user-99/Items')

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


# ===========================================================================
# get_all_available_series
# ===========================================================================

class TestGetAllAvailableSeries(JellyfinTestBase):

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

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_uses_items_endpoint_without_user_id(self, mock_req):
        mock_req.return_value = _make_mock_response({'Items': []})
        with patch.dict(os.environ, {'SERIES_LIBRARY_IDS': ''}):
            get_all_available_series()
        url = mock_req.call_args[0][0]
        self.assertEqual(url, 'Items')

    @patch('services.jellyfinAPIService._make_authenticated_jellyfin_api_request')
    def test_uses_user_items_endpoint_with_user_id(self, mock_req):
        mock_req.return_value = _make_mock_response({'Items': []})
        with patch.dict(os.environ, {'SERIES_LIBRARY_IDS': ''}):
            get_all_available_series(user_id='user-77')
        url = mock_req.call_args[0][0]
        self.assertEqual(url, 'Users/user-77/Items')

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


if __name__ == '__main__':
    unittest.main()

import unittest
from unittest.mock import patch, MagicMock
import os
from datetime import date, timedelta

import services.watchstateAPIService as ws
from services.watchstateAPIService import (
    auth_user,
    _make_authenticated_watchstate_api_request,
    _fetch_all_paginated_data,
    get_user_watched_movies,
    get_user_watched_series,
    _token_cache,
    Series,
    Movie,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_response(data) -> MagicMock:
    """Return a mock requests.Response whose .json() yields *data*."""
    mock = MagicMock()
    mock.json.return_value = data
    return mock


def _page(data_key: str, items: list, next_page=None) -> dict:
    """Build a WatchState paginated response payload."""
    return {
        data_key: list(items),
        'paging': {'next_page': next_page},
    }


def _movie_record(
    title: str = 'Test Movie',
    jellyfin_id: str = 'jf-movie-1',
    tmdb_id: str = '12345',
    played_at: str = None,
    genres: list = None,
    user_key: str = 'jellyfin',
) -> dict:
    today = date.today()
    jf_meta = {
        'id': jellyfin_id,
        'played_at': played_at if played_at is not None else f"{today.isoformat()}T00:00:00Z",
        'extra': {'genres': genres if genres is not None else ['Action']},
    }
    return {
        'title': title,
        'metadata': {user_key: jf_meta},
        'guids': {'guid_tmdb': tmdb_id},
    }


def _episode_record(
    series_title: str = 'Test Series',
    show_id: str = 'show-1',
    tmdb_id: str = '555',
    played_at: str = None,
    genres: list = None,
    user_key: str = 'jellyfin',
) -> dict:
    today = date.today()
    jf_meta = {
        'title': series_title,
        'show': show_id,
        'played_at': played_at if played_at is not None else f"{today.isoformat()}T00:00:00Z",
        'parent': {'guid_tmdb': tmdb_id},
        'extra': {'genres': genres if genres is not None else ['Drama']},
    }
    return {
        'metadata': {user_key: jf_meta},
    }


# ---------------------------------------------------------------------------
# Base class – resets the auth token cache and module global between tests so
# cached auth state does not bleed across cases.
# ---------------------------------------------------------------------------

class WatchStateTestBase(unittest.TestCase):
    def setUp(self):
        _token_cache.clear()
        ws.user_token = None


# ===========================================================================
# auth_user
# ===========================================================================

class TestAuthUser(WatchStateTestBase):

    @patch('services.watchstateAPIService.make_request')
    def test_sets_user_token_from_response(self, mock_make_request):
        mock_make_request.return_value = _make_mock_response({'token': 'tok-123'})
        with patch.dict(os.environ, {'WATCHSTATE_URL': 'http://ws', 'WATCHSTATE_USERNAME': 'u', 'WATCHSTATE_PASSWORD': 'p'}):
            auth_user()
        self.assertEqual(ws.user_token, 'tok-123')

    @patch('services.watchstateAPIService.make_request')
    def test_posts_to_login_endpoint_with_credentials(self, mock_make_request):
        mock_make_request.return_value = _make_mock_response({'token': 't'})
        with patch.dict(os.environ, {'WATCHSTATE_URL': 'http://ws', 'WATCHSTATE_USERNAME': 'alice', 'WATCHSTATE_PASSWORD': 'secret'}):
            auth_user()
        args = mock_make_request.call_args
        self.assertEqual(args[0][0], 'http://ws/v1/api/system/auth/login')
        self.assertEqual(args[0][1], 'POST')
        body = args[1].get('body') or args[0][2]
        self.assertEqual(body['username'], 'alice')
        self.assertEqual(body['password'], 'secret')

    @patch('services.watchstateAPIService.make_request')
    def test_result_is_cached(self, mock_make_request):
        mock_make_request.return_value = _make_mock_response({'token': 't'})
        with patch.dict(os.environ, {'WATCHSTATE_URL': 'http://ws', 'WATCHSTATE_USERNAME': 'u', 'WATCHSTATE_PASSWORD': 'p'}):
            auth_user()
            auth_user()
        mock_make_request.assert_called_once()


# ===========================================================================
# _make_authenticated_watchstate_api_request
# ===========================================================================

class TestMakeAuthenticatedWatchstateApiRequest(WatchStateTestBase):

    @patch('services.watchstateAPIService.make_request')
    @patch('services.watchstateAPIService.auth_user')
    def test_builds_url_with_v1_api_prefix(self, mock_auth, mock_make_request):
        ws.user_token = 'tok'
        mock_make_request.return_value = MagicMock()
        with patch.dict(os.environ, {'WATCHSTATE_URL': 'http://ws'}):
            _make_authenticated_watchstate_api_request('history')
        url = mock_make_request.call_args[0][0]
        self.assertEqual(url, 'http://ws/v1/api/history')

    @patch('services.watchstateAPIService.make_request')
    @patch('services.watchstateAPIService.auth_user')
    def test_injects_token_auth_header(self, mock_auth, mock_make_request):
        ws.user_token = 'my-token'
        mock_make_request.return_value = MagicMock()
        with patch.dict(os.environ, {'WATCHSTATE_URL': 'http://ws'}):
            _make_authenticated_watchstate_api_request('history')
        headers = mock_make_request.call_args[0][4]
        self.assertEqual(headers['Authorization'], 'Token my-token')

    @patch('services.watchstateAPIService.make_request')
    @patch('services.watchstateAPIService.auth_user')
    def test_merges_extra_headers(self, mock_auth, mock_make_request):
        ws.user_token = 'tok'
        mock_make_request.return_value = MagicMock()
        with patch.dict(os.environ, {'WATCHSTATE_URL': 'http://ws'}):
            _make_authenticated_watchstate_api_request('history', headers={'X-User': 'bob'})
        headers = mock_make_request.call_args[0][4]
        self.assertEqual(headers['X-User'], 'bob')
        self.assertIn('Authorization', headers)

    @patch('services.watchstateAPIService.auth_user')
    def test_raises_when_url_missing(self, mock_auth):
        ws.user_token = 'tok'
        with self.assertRaises(Exception) as ctx:
            _make_authenticated_watchstate_api_request('')
        self.assertIn('URL is required', str(ctx.exception))

    @patch('services.watchstateAPIService.auth_user')
    def test_raises_when_token_missing_after_auth(self, mock_auth):
        # auth_user is mocked out so user_token stays None.
        ws.user_token = None
        with self.assertRaises(Exception) as ctx:
            _make_authenticated_watchstate_api_request('history')
        self.assertIn('auth_user', str(ctx.exception))


# ===========================================================================
# _fetch_all_paginated_data
# ===========================================================================

class TestFetchAllPaginatedData(WatchStateTestBase):

    @patch('services.watchstateAPIService._make_authenticated_watchstate_api_request')
    def test_raises_when_data_key_missing_argument(self, mock_req):
        with self.assertRaises(Exception) as ctx:
            _fetch_all_paginated_data('history', params={})
        self.assertIn('data_key is required', str(ctx.exception))

    @patch('services.watchstateAPIService._make_authenticated_watchstate_api_request')
    def test_raises_when_data_key_not_in_response(self, mock_req):
        mock_req.return_value = _make_mock_response({'paging': {'next_page': None}})
        with self.assertRaises(Exception) as ctx:
            _fetch_all_paginated_data('history', params={}, data_key='history')
        self.assertIn('history', str(ctx.exception))

    @patch('services.watchstateAPIService._make_authenticated_watchstate_api_request')
    def test_returns_single_page_when_no_next_page(self, mock_req):
        mock_req.return_value = _make_mock_response(_page('history', [1, 2, 3], next_page=None))
        result = _fetch_all_paginated_data('history', params={}, data_key='history')
        self.assertEqual(result, [1, 2, 3])
        mock_req.assert_called_once()

    @patch('services.watchstateAPIService._make_authenticated_watchstate_api_request')
    def test_follows_next_page_and_concatenates(self, mock_req):
        mock_req.side_effect = [
            _make_mock_response(_page('history', [1, 2], next_page=2)),
            _make_mock_response(_page('history', [3, 4], next_page=3)),
            _make_mock_response(_page('history', [5], next_page=None)),
        ]
        result = _fetch_all_paginated_data('history', params={}, data_key='history')
        self.assertEqual(result, [1, 2, 3, 4, 5])
        self.assertEqual(mock_req.call_count, 3)

    @patch('services.watchstateAPIService._make_authenticated_watchstate_api_request')
    def test_sets_page_param_on_first_request(self, mock_req):
        mock_req.return_value = _make_mock_response(_page('history', [], next_page=None))
        _fetch_all_paginated_data('history', params={'perpage': 100}, data_key='history')
        params = mock_req.call_args[0][2]
        self.assertEqual(params['page'], 1)
        self.assertEqual(params['perpage'], 100)


# ===========================================================================
# get_user_watched_movies
# ===========================================================================

class TestGetUserWatchedMovies(WatchStateTestBase):

    @patch('services.watchstateAPIService._fetch_all_paginated_data')
    def test_returns_movies_with_fields_mapped(self, mock_fetch):
        mock_fetch.return_value = [
            _movie_record('Film A', jellyfin_id='jf-a', tmdb_id='111', genres=['Action', 'Comedy'])
        ]
        with patch.dict(os.environ, {'WATCHSTATE_MAIN_USER_TO_JELLYFIN_MAP': ''}):
            result = get_user_watched_movies('alice')
        self.assertEqual(len(result), 1)
        movie = result[0]
        self.assertEqual(movie.name, 'Film A')
        self.assertEqual(movie.id, 'jf-a')
        self.assertEqual(movie.tmdb_id, '111')
        self.assertEqual(movie.genres, ['action', 'comedy'])

    @patch('services.watchstateAPIService._fetch_all_paginated_data')
    def test_sends_movie_query_params(self, mock_fetch):
        mock_fetch.return_value = []
        with patch.dict(os.environ, {'WATCHSTATE_MAIN_USER_TO_JELLYFIN_MAP': ''}):
            get_user_watched_movies('alice')
        params = mock_fetch.call_args[1]['params']
        self.assertEqual(params['type'], 'movie')
        self.assertEqual(params['watched'], 1)
        self.assertEqual(params['perpage'], 100)

    @patch('services.watchstateAPIService._fetch_all_paginated_data')
    def test_maps_main_user_to_main_header(self, mock_fetch):
        mock_fetch.return_value = []
        with patch.dict(os.environ, {'WATCHSTATE_MAIN_USER_TO_JELLYFIN_MAP': 'alice'}):
            get_user_watched_movies('alice')
        headers = mock_fetch.call_args[1]['headers']
        self.assertEqual(headers['X-User'], 'main')

    @patch('services.watchstateAPIService._fetch_all_paginated_data')
    def test_uses_username_header_for_non_main_user(self, mock_fetch):
        mock_fetch.return_value = []
        with patch.dict(os.environ, {'WATCHSTATE_MAIN_USER_TO_JELLYFIN_MAP': 'someone-else'}):
            get_user_watched_movies('bob')
        headers = mock_fetch.call_args[1]['headers']
        self.assertEqual(headers['X-User'], 'bob')

    @patch('services.watchstateAPIService._fetch_all_paginated_data')
    def test_skips_record_without_jellyfin_metadata(self, mock_fetch):
        bad = {'title': 'No JF', 'metadata': {}, 'guids': {'guid_tmdb': '1'}}
        good = _movie_record('Good')
        mock_fetch.return_value = [bad, good]
        with patch.dict(os.environ, {'WATCHSTATE_MAIN_USER_TO_JELLYFIN_MAP': ''}):
            result = get_user_watched_movies('alice')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, 'Good')

    @patch('services.watchstateAPIService._fetch_all_paginated_data')
    def test_skips_record_without_played_at(self, mock_fetch):
        rec = _movie_record('No Date', played_at='')
        mock_fetch.return_value = [rec]
        with patch.dict(os.environ, {'WATCHSTATE_MAIN_USER_TO_JELLYFIN_MAP': ''}):
            result = get_user_watched_movies('alice')
        self.assertEqual(result, [])

    @patch('services.watchstateAPIService._fetch_all_paginated_data')
    def test_prefers_user_specific_metadata_key(self, mock_fetch):
        # metadata keyed on jellyfin_<user> should win over the generic key.
        rec = _movie_record('User Specific', jellyfin_id='specific', user_key='jellyfin_alice')
        mock_fetch.return_value = [rec]
        with patch.dict(os.environ, {'WATCHSTATE_MAIN_USER_TO_JELLYFIN_MAP': ''}):
            result = get_user_watched_movies('alice')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, 'specific')

    @patch('services.watchstateAPIService._fetch_all_paginated_data')
    def test_parses_epoch_timestamp_played_at(self, mock_fetch):
        # A numeric epoch string takes the except branch (fromtimestamp).
        recent_epoch = str(int(__import__('time').time()))
        rec = _movie_record('Epoch', played_at=recent_epoch)
        mock_fetch.return_value = [rec]
        with patch.dict(os.environ, {'WATCHSTATE_MAIN_USER_TO_JELLYFIN_MAP': ''}):
            result = get_user_watched_movies('alice', max_lookback_days=30)
        self.assertEqual(len(result), 1)

    @patch('services.watchstateAPIService._fetch_all_paginated_data')
    def test_excludes_movies_outside_lookback_window(self, mock_fetch):
        old_date = (date.today() - timedelta(days=90)).isoformat()
        rec = _movie_record('Old', played_at=f"{old_date}T00:00:00Z")
        mock_fetch.return_value = [rec]
        with patch.dict(os.environ, {'WATCHSTATE_MAIN_USER_TO_JELLYFIN_MAP': ''}):
            result = get_user_watched_movies('alice', max_lookback_days=30)
        self.assertEqual(result, [])

    @patch('services.watchstateAPIService._fetch_all_paginated_data')
    def test_includes_movies_within_lookback_window(self, mock_fetch):
        recent_date = (date.today() - timedelta(days=5)).isoformat()
        rec = _movie_record('Recent', played_at=f"{recent_date}T00:00:00Z")
        mock_fetch.return_value = [rec]
        with patch.dict(os.environ, {'WATCHSTATE_MAIN_USER_TO_JELLYFIN_MAP': ''}):
            result = get_user_watched_movies('alice', max_lookback_days=30)
        self.assertEqual(len(result), 1)


# ===========================================================================
# get_user_watched_series
# ===========================================================================

class TestGetUserWatchedSeries(WatchStateTestBase):

    @patch('services.watchstateAPIService._fetch_all_paginated_data')
    def test_returns_series_meeting_min_episode_count(self, mock_fetch):
        episodes = [_episode_record('Breaking Bad', show_id='bb', tmdb_id='999')] * 3
        mock_fetch.return_value = episodes
        with patch.dict(os.environ, {'WATCHSTATE_MAIN_USER_TO_JELLYFIN_MAP': ''}):
            result = get_user_watched_series('alice', min_episode_watch_count=3)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, 'Breaking Bad')
        self.assertEqual(result[0].id, 'bb')
        self.assertEqual(result[0].tmdb_id, '999')

    @patch('services.watchstateAPIService._fetch_all_paginated_data')
    def test_excludes_series_below_min_episode_count(self, mock_fetch):
        episodes = [_episode_record('Breaking Bad', show_id='bb')] * 2
        mock_fetch.return_value = episodes
        with patch.dict(os.environ, {'WATCHSTATE_MAIN_USER_TO_JELLYFIN_MAP': ''}):
            result = get_user_watched_series('alice', min_episode_watch_count=3)
        self.assertEqual(result, [])

    @patch('services.watchstateAPIService._fetch_all_paginated_data')
    def test_sends_series_query_params(self, mock_fetch):
        mock_fetch.return_value = []
        with patch.dict(os.environ, {'WATCHSTATE_MAIN_USER_TO_JELLYFIN_MAP': ''}):
            get_user_watched_series('alice', min_episode_watch_count=1)
        params = mock_fetch.call_args[1]['params']
        self.assertEqual(params['type'], 'series')
        self.assertEqual(params['watched'], 1)
        self.assertEqual(params['perpage'], 200)

    @patch('services.watchstateAPIService._fetch_all_paginated_data')
    def test_lowercases_genres(self, mock_fetch):
        episodes = [_episode_record('Show', show_id='s1', genres=['Sci-Fi', 'Drama'])]
        mock_fetch.return_value = episodes
        with patch.dict(os.environ, {'WATCHSTATE_MAIN_USER_TO_JELLYFIN_MAP': ''}):
            result = get_user_watched_series('alice', min_episode_watch_count=1)
        self.assertEqual(result[0].genres, ['sci-fi', 'drama'])

    @patch('services.watchstateAPIService._fetch_all_paginated_data')
    def test_skips_episodes_without_jellyfin_metadata(self, mock_fetch):
        bad = {'metadata': {}}
        good = _episode_record('Good', show_id='good')
        mock_fetch.return_value = [bad, good]
        with patch.dict(os.environ, {'WATCHSTATE_MAIN_USER_TO_JELLYFIN_MAP': ''}):
            result = get_user_watched_series('alice', min_episode_watch_count=1)
        ids = [s.id for s in result]
        self.assertEqual(ids, ['good'])

    @patch('services.watchstateAPIService._fetch_all_paginated_data')
    def test_skips_episodes_without_played_at(self, mock_fetch):
        rec = _episode_record('No Date', show_id='nd', played_at='')
        mock_fetch.return_value = [rec]
        with patch.dict(os.environ, {'WATCHSTATE_MAIN_USER_TO_JELLYFIN_MAP': ''}):
            result = get_user_watched_series('alice', min_episode_watch_count=1)
        self.assertEqual(result, [])

    @patch('services.watchstateAPIService._fetch_all_paginated_data')
    def test_excludes_episodes_outside_lookback_window(self, mock_fetch):
        old_date = (date.today() - timedelta(days=90)).isoformat()
        episodes = [_episode_record('Old', show_id='old', played_at=f"{old_date}T00:00:00Z")] * 3
        mock_fetch.return_value = episodes
        with patch.dict(os.environ, {'WATCHSTATE_MAIN_USER_TO_JELLYFIN_MAP': ''}):
            result = get_user_watched_series('alice', max_lookback_days=30, min_episode_watch_count=1)
        self.assertEqual(result, [])

    @patch('services.watchstateAPIService._fetch_all_paginated_data')
    def test_deduplicates_episodes_into_single_series(self, mock_fetch):
        episodes = [
            _episode_record('Show A', show_id='a'),
            _episode_record('Show A', show_id='a'),
            _episode_record('Show B', show_id='b'),
        ]
        mock_fetch.return_value = episodes
        with patch.dict(os.environ, {'WATCHSTATE_MAIN_USER_TO_JELLYFIN_MAP': ''}):
            result = get_user_watched_series('alice', min_episode_watch_count=2)
        ids = [s.id for s in result]
        self.assertEqual(ids, ['a'])

    @patch('services.watchstateAPIService._fetch_all_paginated_data')
    def test_maps_main_user_to_main_header(self, mock_fetch):
        mock_fetch.return_value = []
        with patch.dict(os.environ, {'WATCHSTATE_MAIN_USER_TO_JELLYFIN_MAP': 'alice'}):
            get_user_watched_series('alice', min_episode_watch_count=1)
        headers = mock_fetch.call_args[1]['headers']
        self.assertEqual(headers['X-User'], 'main')

    @patch('services.watchstateAPIService._fetch_all_paginated_data')
    def test_parses_epoch_timestamp_played_at(self, mock_fetch):
        # A numeric epoch string takes the except branch (fromtimestamp).
        recent_epoch = str(int(__import__('time').time()))
        episodes = [_episode_record('Epoch Show', show_id='epoch', played_at=recent_epoch)]
        mock_fetch.return_value = episodes
        with patch.dict(os.environ, {'WATCHSTATE_MAIN_USER_TO_JELLYFIN_MAP': ''}):
            result = get_user_watched_series('alice', max_lookback_days=30, min_episode_watch_count=1)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, 'epoch')


if __name__ == '__main__':
    unittest.main()

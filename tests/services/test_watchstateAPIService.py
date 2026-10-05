import unittest
from unittest.mock import patch, MagicMock
import os
import time
from datetime import date, timedelta

import requests

import services.watchstateAPIService as ws
from services.watchstateAPIService import (
    auth_user,
    _login,
    refresh_token,
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


def _http_error(status: int) -> requests.exceptions.HTTPError:
    """Build an HTTPError carrying a response with the given status code."""
    resp = MagicMock()
    resp.status_code = status
    return requests.exceptions.HTTPError(response=resp)


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
        self.assertEqual(params['view'], ws._HISTORY_VIEW_FIELDS)

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
        # The WatchState history API types are only movie/episode; shows are
        # queried as their episodes.
        self.assertEqual(params['type'], 'episode')
        self.assertEqual(params['watched'], 1)
        self.assertEqual(params['perpage'], 200)
        self.assertEqual(params['view'], ws._HISTORY_VIEW_FIELDS)

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


# ===========================================================================
# Non-dict / missing guid handling + skip-no-tmdb (hardening #1, #2, #3)
# ===========================================================================

class TestMovieGuidHardening(WatchStateTestBase):

    def _record(self, guids, played_at=None):
        today = date.today()
        return {
            'title': 'Film',
            'metadata': {'jellyfin': {
                'id': 'jf-1',
                'played_at': played_at if played_at is not None else f"{today.isoformat()}T00:00:00Z",
                'extra': {'genres': ['Action']},
            }},
            'guids': guids,
        }

    @patch('services.watchstateAPIService._fetch_all_paginated_data')
    def test_skips_movie_when_guids_is_list(self, mock_fetch):
        # Top-level `guids` can be an empty list for some records; must not crash.
        mock_fetch.return_value = [self._record(guids=[])]
        with patch.dict(os.environ, {'WATCHSTATE_MAIN_USER_TO_JELLYFIN_MAP': ''}):
            result = get_user_watched_movies('alice')
        self.assertEqual(result, [])

    @patch('services.watchstateAPIService._fetch_all_paginated_data')
    def test_skips_movie_without_tmdb_id(self, mock_fetch):
        mock_fetch.return_value = [self._record(guids={'guid_imdb': 'tt1'})]
        with patch.dict(os.environ, {'WATCHSTATE_MAIN_USER_TO_JELLYFIN_MAP': ''}):
            result = get_user_watched_movies('alice')
        self.assertEqual(result, [])

    @patch('services.watchstateAPIService._fetch_all_paginated_data')
    def test_keeps_movie_with_tmdb_id(self, mock_fetch):
        mock_fetch.return_value = [self._record(guids={'guid_tmdb': '42'})]
        with patch.dict(os.environ, {'WATCHSTATE_MAIN_USER_TO_JELLYFIN_MAP': ''}):
            result = get_user_watched_movies('alice')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].tmdb_id, '42')

    @patch('services.watchstateAPIService._fetch_all_paginated_data')
    def test_parses_int_epoch_played_at(self, mock_fetch):
        # Movies can return played_at as an int; parse_jellyfin_date raises
        # AttributeError which must be caught and fall through to fromtimestamp.
        rec = self._record(guids={'guid_tmdb': '42'}, played_at=int(time.time()))
        mock_fetch.return_value = [rec]
        with patch.dict(os.environ, {'WATCHSTATE_MAIN_USER_TO_JELLYFIN_MAP': ''}):
            result = get_user_watched_movies('alice', max_lookback_days=30)
        self.assertEqual(len(result), 1)


class TestSeriesParentHardening(WatchStateTestBase):

    def _episode(self, parent, show_id='show-1', played_at=None):
        today = date.today()
        return {
            'metadata': {'jellyfin': {
                'title': 'Show',
                'show': show_id,
                'played_at': played_at if played_at is not None else f"{today.isoformat()}T00:00:00Z",
                'parent': parent,
                'extra': {'genres': ['Drama']},
            }},
        }

    @patch('services.watchstateAPIService._fetch_all_paginated_data')
    def test_skips_episode_when_parent_is_list(self, mock_fetch):
        # The real crash: parent came back as an empty list ([].get -> error).
        mock_fetch.return_value = [self._episode(parent=[])]
        with patch.dict(os.environ, {'WATCHSTATE_MAIN_USER_TO_JELLYFIN_MAP': ''}):
            result = get_user_watched_series('alice', min_episode_watch_count=1)
        self.assertEqual(result, [])

    @patch('services.watchstateAPIService._fetch_all_paginated_data')
    def test_skips_episode_when_parent_missing(self, mock_fetch):
        ep = self._episode(parent=None)
        ep['metadata']['jellyfin'].pop('parent')
        mock_fetch.return_value = [ep]
        with patch.dict(os.environ, {'WATCHSTATE_MAIN_USER_TO_JELLYFIN_MAP': ''}):
            result = get_user_watched_series('alice', min_episode_watch_count=1)
        self.assertEqual(result, [])

    @patch('services.watchstateAPIService._fetch_all_paginated_data')
    def test_skips_episode_without_parent_tmdb(self, mock_fetch):
        mock_fetch.return_value = [self._episode(parent={'guid_tvdb': '900'})]
        with patch.dict(os.environ, {'WATCHSTATE_MAIN_USER_TO_JELLYFIN_MAP': ''}):
            result = get_user_watched_series('alice', min_episode_watch_count=1)
        self.assertEqual(result, [])

    @patch('services.watchstateAPIService._fetch_all_paginated_data')
    def test_no_tmdb_episodes_do_not_count_toward_series(self, mock_fetch):
        # Two good episodes of one show + one no-tmdb episode of another; only
        # the show meeting the min count via tmdb-bearing episodes survives.
        good = [self._episode(parent={'guid_tmdb': '7'}, show_id='good')] * 2
        junk = [self._episode(parent=[], show_id='junk')] * 5
        mock_fetch.return_value = good + junk
        with patch.dict(os.environ, {'WATCHSTATE_MAIN_USER_TO_JELLYFIN_MAP': ''}):
            result = get_user_watched_series('alice', min_episode_watch_count=2)
        self.assertEqual([s.id for s in result], ['good'])


# ===========================================================================
# _fetch_all_paginated_data response-shape guards (hardening #4, #5)
# ===========================================================================

class TestFetchAllPaginatedDataHardening(WatchStateTestBase):

    @patch('services.watchstateAPIService._make_authenticated_watchstate_api_request')
    def test_missing_paging_treated_as_single_page(self, mock_req):
        # No paging key at all -> return page 1 items, no crash.
        mock_req.return_value = _make_mock_response({'history': [1, 2, 3]})
        result = _fetch_all_paginated_data('history', params={}, data_key='history')
        self.assertEqual(result, [1, 2, 3])
        mock_req.assert_called_once()

    @patch('services.watchstateAPIService._make_authenticated_watchstate_api_request')
    def test_non_dict_response_raises_clear_error(self, mock_req):
        mock_req.return_value = _make_mock_response([1, 2, 3])
        with self.assertRaises(Exception) as ctx:
            _fetch_all_paginated_data('history', params={}, data_key='history')
        self.assertIn('history', str(ctx.exception))
        self.assertIn('page 1', str(ctx.exception))

    @patch('services.watchstateAPIService._make_authenticated_watchstate_api_request')
    def test_non_list_data_key_raises_clear_error(self, mock_req):
        mock_req.return_value = _make_mock_response({'history': {'nope': 1}, 'paging': {'next_page': None}})
        with self.assertRaises(Exception) as ctx:
            _fetch_all_paginated_data('history', params={}, data_key='history')
        self.assertIn('list', str(ctx.exception))

    @patch('services.watchstateAPIService._make_authenticated_watchstate_api_request')
    def test_malformed_later_page_raises_with_page_number(self, mock_req):
        mock_req.side_effect = [
            _make_mock_response(_page('history', [1, 2], next_page=2)),
            _make_mock_response({'paging': {'next_page': None}}),  # history missing on page 2
        ]
        with self.assertRaises(Exception) as ctx:
            _fetch_all_paginated_data('history', params={}, data_key='history')
        self.assertIn('page 2', str(ctx.exception))

    @patch('services.watchstateAPIService._make_authenticated_watchstate_api_request')
    def test_passes_params_through_on_each_page(self, mock_req):
        mock_req.side_effect = [
            _make_mock_response(_page('history', [1], next_page=2)),
            _make_mock_response(_page('history', [2], next_page=None)),
        ]
        _fetch_all_paginated_data('history', params={'perpage': 50}, data_key='history')
        # Both pages carry perpage and the correct page number.
        first_params = mock_req.call_args_list[0][0][2]
        second_params = mock_req.call_args_list[1][0][2]
        self.assertEqual(first_params['perpage'], 50)
        self.assertEqual(first_params['page'], 1)
        self.assertEqual(second_params['perpage'], 50)
        self.assertEqual(second_params['page'], 2)


# ===========================================================================
# _login / refresh_token (token refresh with re-login fallback, #8)
# ===========================================================================

class TestLoginAndRefresh(WatchStateTestBase):

    @patch('services.watchstateAPIService.make_request')
    def test_login_sets_and_returns_token(self, mock_req):
        mock_req.return_value = _make_mock_response({'token': 'tok-1'})
        with patch.dict(os.environ, {'WATCHSTATE_URL': 'http://ws', 'WATCHSTATE_USERNAME': 'u', 'WATCHSTATE_PASSWORD': 'p'}):
            out = _login()
        self.assertEqual(out, 'tok-1')
        self.assertEqual(ws.user_token, 'tok-1')

    @patch('services.watchstateAPIService.make_request')
    def test_refresh_uses_refresh_endpoint_with_current_token(self, mock_req):
        ws.user_token = 'old'
        mock_req.return_value = _make_mock_response({'token': 'new'})
        with patch.dict(os.environ, {'WATCHSTATE_URL': 'http://ws'}):
            out = refresh_token()
        self.assertEqual(out, 'new')
        self.assertEqual(ws.user_token, 'new')
        url = mock_req.call_args[0][0]
        headers = mock_req.call_args.kwargs.get('headers') or {}
        self.assertEqual(url, 'http://ws/v1/api/system/auth/refresh')
        self.assertEqual(headers.get('Authorization'), 'Token old')

    @patch('services.watchstateAPIService._login', return_value='fresh')
    def test_refresh_without_current_token_relogins(self, mock_login):
        ws.user_token = None
        out = refresh_token()
        self.assertEqual(out, 'fresh')
        mock_login.assert_called_once()

    @patch('services.watchstateAPIService._login', return_value='fresh')
    @patch('services.watchstateAPIService.make_request')
    def test_refresh_failure_falls_back_to_login_and_logs(self, mock_req, mock_login):
        ws.user_token = 'old'
        mock_req.side_effect = _http_error(401)
        with patch.dict(os.environ, {'WATCHSTATE_URL': 'http://ws'}), \
             patch.object(ws.logger, 'warning') as mock_warn:
            out = refresh_token()
        self.assertEqual(out, 'fresh')
        mock_login.assert_called_once()
        self.assertTrue(mock_warn.called)

    @patch('services.watchstateAPIService._login', return_value='fresh')
    @patch('services.watchstateAPIService.make_request')
    def test_refresh_response_without_token_falls_back(self, mock_req, mock_login):
        ws.user_token = 'old'
        mock_req.return_value = _make_mock_response({'no_token': True})
        with patch.dict(os.environ, {'WATCHSTATE_URL': 'http://ws'}), \
             patch.object(ws.logger, 'warning'):
            out = refresh_token()
        self.assertEqual(out, 'fresh')
        mock_login.assert_called_once()


# ===========================================================================
# 401 retry / compare-and-refresh in request path (#9)
# ===========================================================================

class TestRequest401Retry(WatchStateTestBase):

    @patch('services.watchstateAPIService.auth_user')
    @patch('services.watchstateAPIService.refresh_token')
    @patch('services.watchstateAPIService.make_request')
    def test_401_triggers_refresh_and_retries_once(self, mock_req, mock_refresh, mock_auth):
        ws.user_token = 'old'

        def refresh_side():
            ws.user_token = 'new'
            return 'new'
        mock_refresh.side_effect = refresh_side

        ok = MagicMock()
        mock_req.side_effect = [_http_error(401), ok]
        with patch.dict(os.environ, {'WATCHSTATE_URL': 'http://ws'}):
            out = _make_authenticated_watchstate_api_request('history')
        self.assertIs(out, ok)
        mock_refresh.assert_called_once()
        self.assertEqual(mock_req.call_count, 2)

    @patch('services.watchstateAPIService.auth_user')
    @patch('services.watchstateAPIService.refresh_token')
    @patch('services.watchstateAPIService.make_request')
    def test_non_401_propagates_without_refresh(self, mock_req, mock_refresh, mock_auth):
        ws.user_token = 'tok'
        mock_req.side_effect = _http_error(500)
        with patch.dict(os.environ, {'WATCHSTATE_URL': 'http://ws'}):
            with self.assertRaises(requests.exceptions.HTTPError):
                _make_authenticated_watchstate_api_request('history')
        mock_refresh.assert_not_called()

    @patch('services.watchstateAPIService.auth_user')
    @patch('services.watchstateAPIService.refresh_token')
    @patch('services.watchstateAPIService.make_request')
    def test_compare_and_refresh_skips_when_token_already_rotated(self, mock_req, mock_refresh, mock_auth):
        # Simulate another thread rotating the token between the failed attempt
        # and the retry handler acquiring the lock -> no refresh should happen.
        ws.user_token = 'tokA'
        ok = MagicMock()

        def side(*a, **k):
            if mock_req.call_count == 1:
                ws.user_token = 'tokB'  # rotated elsewhere
                raise _http_error(401)
            return ok
        mock_req.side_effect = side
        with patch.dict(os.environ, {'WATCHSTATE_URL': 'http://ws'}):
            out = _make_authenticated_watchstate_api_request('history')
        self.assertIs(out, ok)
        mock_refresh.assert_not_called()

    @patch('services.watchstateAPIService.auth_user')
    @patch('services.watchstateAPIService.make_request')
    def test_injects_token_header(self, mock_req, mock_auth):
        ws.user_token = 'my-token'
        mock_req.return_value = MagicMock()
        with patch.dict(os.environ, {'WATCHSTATE_URL': 'http://ws'}):
            _make_authenticated_watchstate_api_request('history')
        headers = mock_req.call_args[0][4]
        self.assertEqual(headers['Authorization'], 'Token my-token')


if __name__ == '__main__':
    unittest.main()

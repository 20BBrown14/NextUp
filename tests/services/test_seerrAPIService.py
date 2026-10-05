import unittest
from unittest.mock import patch, MagicMock
import os
from services.seerrAPIService import (
    get_seerr_users,
    make_media_request,
    import_jellyfin_user,
    get_or_create_seerr_user_by_jellyfin_id,
    _make_authenticated_seerr_api_request,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_response(data) -> MagicMock:
    """Return a mock requests.Response whose .json() yields *data*."""
    mock = MagicMock()
    mock.json.return_value = data
    return mock


def _make_user(user_id: int = 1, jellyfin_user_id: str = None) -> dict:
    user = {
        'id': user_id,
        'email': f'user{user_id}@example.com',
        'createdAt': '2026-01-01T00:00:00.000Z',
        'updatedAt': '2026-01-01T00:00:00.000Z',
    }
    if jellyfin_user_id is not None:
        user['jellyfinUserId'] = jellyfin_user_id
    return user


# ===========================================================================
# _make_authenticated_seerr_api_request
# ===========================================================================

class TestMakeAuthenticatedSeerrApiRequest(unittest.TestCase):

    @patch('services.seerrAPIService.make_request')
    def test_builds_url_with_api_v1_prefix(self, mock_make_request):
        mock_make_request.return_value = MagicMock()
        with patch.dict(os.environ, {'SEERR_API_KEY': 'key', 'SEERR_URL': 'http://seerr.local'}):
            _make_authenticated_seerr_api_request('user')
        url = mock_make_request.call_args[0][0]
        self.assertEqual(url, 'http://seerr.local/api/v1/user')

    @patch('services.seerrAPIService.make_request')
    def test_injects_x_api_key_header(self, mock_make_request):
        mock_make_request.return_value = MagicMock()
        with patch.dict(os.environ, {'SEERR_API_KEY': 'my-token', 'SEERR_URL': 'http://seerr'}):
            _make_authenticated_seerr_api_request('user')
        headers = mock_make_request.call_args[0][4]
        self.assertEqual(headers['X-Api-Key'], 'my-token')

    @patch('services.seerrAPIService.make_request')
    def test_merges_extra_headers(self, mock_make_request):
        mock_make_request.return_value = MagicMock()
        with patch.dict(os.environ, {'SEERR_API_KEY': 'k', 'SEERR_URL': 'http://seerr'}):
            _make_authenticated_seerr_api_request('user', headers={'X-Custom': 'yes'})
        headers = mock_make_request.call_args[0][4]
        self.assertEqual(headers['X-Custom'], 'yes')
        self.assertIn('X-Api-Key', headers)

    @patch('services.seerrAPIService.make_request')
    def test_passes_params_body_and_method(self, mock_make_request):
        mock_make_request.return_value = MagicMock()
        with patch.dict(os.environ, {'SEERR_API_KEY': 'k', 'SEERR_URL': 'http://seerr'}):
            _make_authenticated_seerr_api_request('request', method='POST', params={'p': 1}, body={'b': 2})
        args = mock_make_request.call_args[0]
        self.assertEqual(args[1], 'POST')
        self.assertEqual(args[2], {'p': 1})
        self.assertEqual(args[3], {'b': 2})


# ===========================================================================
# get_seerr_users
# ===========================================================================

class TestGetSeerrUsers(unittest.TestCase):

    @patch('services.seerrAPIService._make_authenticated_seerr_api_request')
    def test_returns_results_list(self, mock_req):
        users = [_make_user(1), _make_user(2)]
        mock_req.return_value = _make_mock_response({'results': users})
        result = get_seerr_users()
        self.assertEqual(result, users)

    @patch('services.seerrAPIService._make_authenticated_seerr_api_request')
    def test_calls_correct_endpoint(self, mock_req):
        mock_req.return_value = _make_mock_response({'results': []})
        get_seerr_users()
        url = mock_req.call_args[0][0]
        self.assertEqual(url, 'user')

    @patch('services.seerrAPIService._make_authenticated_seerr_api_request')
    def test_passes_take_param(self, mock_req):
        mock_req.return_value = _make_mock_response({'results': []})
        get_seerr_users()
        params = mock_req.call_args[1].get('params') or mock_req.call_args[0][2]
        self.assertEqual(params['take'], 100)

    @patch('services.seerrAPIService._make_authenticated_seerr_api_request')
    def test_returns_none_when_results_missing(self, mock_req):
        mock_req.return_value = _make_mock_response({})
        result = get_seerr_users()
        self.assertIsNone(result)


# ===========================================================================
# make_media_request
# ===========================================================================

class TestMakeMediaRequest(unittest.TestCase):

    @patch('services.seerrAPIService._make_authenticated_seerr_api_request')
    def test_raises_when_tmdb_id_missing(self, mock_req):
        with self.assertRaises(Exception) as ctx:
            make_media_request(tmdb_id=0, media_type='movie', seerr_user_id=5)
        self.assertIn('required', str(ctx.exception))

    @patch('services.seerrAPIService._make_authenticated_seerr_api_request')
    def test_raises_when_seerr_user_id_missing(self, mock_req):
        with self.assertRaises(Exception) as ctx:
            make_media_request(tmdb_id=123, media_type='movie', seerr_user_id=0)
        self.assertIn('required', str(ctx.exception))

    @patch('services.seerrAPIService._make_authenticated_seerr_api_request')
    def test_raises_on_invalid_media_type(self, mock_req):
        with self.assertRaises(Exception) as ctx:
            make_media_request(tmdb_id=123, media_type='anime', seerr_user_id=5)
        self.assertIn("['movie', tv']", str(ctx.exception))

    @patch('services.seerrAPIService._make_authenticated_seerr_api_request')
    def test_builds_movie_request_body(self, mock_req):
        mock_req.return_value = _make_mock_response({'id': 1})
        make_media_request(tmdb_id=123, media_type='movie', seerr_user_id=5)
        body = mock_req.call_args[1].get('body') or mock_req.call_args[0][3]
        self.assertEqual(body['mediaType'], 'movie')
        self.assertEqual(body['mediaId'], 123)
        self.assertEqual(body['userId'], 5)
        self.assertNotIn('seasons', body)

    @patch('services.seerrAPIService._make_authenticated_seerr_api_request')
    def test_builds_tv_request_body_with_default_seasons(self, mock_req):
        mock_req.return_value = _make_mock_response({'id': 1})
        make_media_request(tmdb_id=456, media_type='tv', seerr_user_id=5)
        body = mock_req.call_args[1].get('body') or mock_req.call_args[0][3]
        self.assertEqual(body['mediaType'], 'tv')
        self.assertEqual(body['seasons'], [1])

    @patch('services.seerrAPIService._make_authenticated_seerr_api_request')
    def test_builds_tv_request_body_with_custom_seasons(self, mock_req):
        mock_req.return_value = _make_mock_response({'id': 1})
        make_media_request(tmdb_id=456, media_type='tv', seerr_user_id=5, seasons=[1, 2, 3])
        body = mock_req.call_args[1].get('body') or mock_req.call_args[0][3]
        self.assertEqual(body['seasons'], [1, 2, 3])

    @patch('services.seerrAPIService._make_authenticated_seerr_api_request')
    def test_posts_to_request_endpoint(self, mock_req):
        mock_req.return_value = _make_mock_response({'id': 1})
        make_media_request(tmdb_id=123, media_type='movie', seerr_user_id=5)
        url = mock_req.call_args[0][0]
        method = mock_req.call_args[1].get('method') or mock_req.call_args[0][1]
        self.assertEqual(url, 'request')
        self.assertEqual(method, 'POST')

    @patch('services.seerrAPIService.get_or_create_seerr_user_by_jellyfin_id')
    @patch('services.seerrAPIService._make_authenticated_seerr_api_request')
    def test_resolves_seerr_user_id_from_jellyfin_id(self, mock_req, mock_resolve):
        mock_resolve.return_value = 42
        mock_req.return_value = _make_mock_response({'id': 1})
        make_media_request(
            tmdb_id=123, media_type='movie', seerr_user_id=None,
            jellyfin_user_id='jf-abc', auto_create_user=True
        )
        mock_resolve.assert_called_once_with(jellyfin_user_id='jf-abc', auto_create=True)
        body = mock_req.call_args[1].get('body') or mock_req.call_args[0][3]
        self.assertEqual(body['userId'], 42)

    @patch('services.seerrAPIService.get_or_create_seerr_user_by_jellyfin_id')
    @patch('services.seerrAPIService._make_authenticated_seerr_api_request')
    def test_returns_json_response(self, mock_req, mock_resolve):
        mock_req.return_value = _make_mock_response({'id': 99, 'status': 1})
        result = make_media_request(tmdb_id=123, media_type='movie', seerr_user_id=5)
        self.assertEqual(result, {'id': 99, 'status': 1})


# ===========================================================================
# import_jellyfin_user
# ===========================================================================

class TestImportJellyfinUser(unittest.TestCase):

    @patch('services.seerrAPIService._make_authenticated_seerr_api_request')
    def test_strips_hyphens_from_id(self, mock_req):
        mock_req.return_value = _make_mock_response([_make_user(1)])
        import_jellyfin_user('a1b2-c3d4-e5f6')
        body = mock_req.call_args[1].get('body') or mock_req.call_args[0][3]
        self.assertEqual(body['jellyfinUserIds'], ['a1b2c3d4e5f6'])

    @patch('services.seerrAPIService._make_authenticated_seerr_api_request')
    def test_posts_to_import_endpoint(self, mock_req):
        mock_req.return_value = _make_mock_response([])
        import_jellyfin_user('abc')
        url = mock_req.call_args[0][0]
        method = mock_req.call_args[1].get('method') or mock_req.call_args[0][1]
        self.assertEqual(url, 'user/import-from-jellyfin')
        self.assertEqual(method, 'POST')

    @patch('services.seerrAPIService._make_authenticated_seerr_api_request')
    def test_returns_json_response(self, mock_req):
        imported = [_make_user(7)]
        mock_req.return_value = _make_mock_response(imported)
        result = import_jellyfin_user('abc')
        self.assertEqual(result, imported)


# ===========================================================================
# get_or_create_seerr_user_by_jellyfin_id
# ===========================================================================

class TestGetOrCreateSeerrUserByJellyfinId(unittest.TestCase):

    @patch('services.seerrAPIService.get_seerr_users')
    def test_returns_id_of_existing_user(self, mock_users):
        mock_users.return_value = [
            _make_user(1, jellyfin_user_id='other'),
            _make_user(2, jellyfin_user_id='a1b2c3d4'),
        ]
        result = get_or_create_seerr_user_by_jellyfin_id('a1b2-c3d4')
        self.assertEqual(result, 2)

    @patch('services.seerrAPIService.get_seerr_users')
    def test_matches_ignoring_hyphens(self, mock_users):
        # Stored ID has hyphens, lookup ID does not – should still match.
        mock_users.return_value = [_make_user(3, jellyfin_user_id='a1b2-c3d4')]
        result = get_or_create_seerr_user_by_jellyfin_id('a1b2c3d4')
        self.assertEqual(result, 3)

    @patch('services.seerrAPIService.get_seerr_users')
    def test_handles_users_without_jellyfin_id(self, mock_users):
        # A user with no jellyfinUserId key must not raise.
        mock_users.return_value = [
            _make_user(1),
            _make_user(2, jellyfin_user_id='match'),
        ]
        result = get_or_create_seerr_user_by_jellyfin_id('match')
        self.assertEqual(result, 2)

    @patch('services.seerrAPIService.get_seerr_users')
    def test_handles_none_user_list(self, mock_users):
        # get_seerr_users returning None must be treated as empty.
        mock_users.return_value = None
        with self.assertRaises(Exception):
            get_or_create_seerr_user_by_jellyfin_id('missing', auto_create=False)

    @patch('services.seerrAPIService.import_jellyfin_user')
    @patch('services.seerrAPIService.get_seerr_users')
    def test_auto_creates_when_missing_and_enabled(self, mock_users, mock_import):
        mock_users.return_value = []
        mock_import.return_value = [_make_user(55)]
        result = get_or_create_seerr_user_by_jellyfin_id('new-user', auto_create=True)
        mock_import.assert_called_once_with('new-user')
        self.assertEqual(result, 55)

    @patch('services.seerrAPIService.import_jellyfin_user')
    @patch('services.seerrAPIService.get_seerr_users')
    def test_raises_when_auto_create_import_returns_empty(self, mock_users, mock_import):
        mock_users.return_value = []
        mock_import.return_value = []
        with self.assertRaises(Exception) as ctx:
            get_or_create_seerr_user_by_jellyfin_id('new-user', auto_create=True)
        self.assertIn('Failed to auto-import', str(ctx.exception))

    @patch('services.seerrAPIService.get_seerr_users')
    def test_raises_when_missing_and_auto_create_disabled(self, mock_users):
        mock_users.return_value = []
        with self.assertRaises(Exception) as ctx:
            get_or_create_seerr_user_by_jellyfin_id('new-user', auto_create=False)
        self.assertIn('auto-creation is disabled', str(ctx.exception))


if __name__ == '__main__':
    unittest.main()

import unittest
from unittest.mock import patch, MagicMock, call
import os
from services.tmdbAPIService import (
    get_tv_genres,
    get_movie_genres,
    get_recommendations_by_id,
    get_popular_series,
    get_popular_movies,
    get_upcoming_movies,
    _make_authenticated_tmdb_api_request,
    _genre_cache,
    _recommendations_cache,
    _trending_cache,
)
from constants.tmdb import TMDB_SECRET_KEYS
from constants.config import CONFIG_KEYS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_response(data: dict) -> MagicMock:
    """Return a mock requests.Response whose .json() yields *data*."""
    mock = MagicMock()
    mock.json.return_value = data
    return mock


def _make_reco(
    id: int = 1,
    vote_average: float = 8.0,
    vote_count: int = 100,
    original_language: str = 'en',
) -> dict:
    return {
        'id': id,
        'vote_average': vote_average,
        'vote_count': vote_count,
        'original_language': original_language,
    }


# ---------------------------------------------------------------------------
# Base class that clears all caches before every test so caching side-effects
# don't bleed between test cases.
# ---------------------------------------------------------------------------

class TMDBTestBase(unittest.TestCase):
    def setUp(self):
        _genre_cache.clear()
        _recommendations_cache.clear()
        _trending_cache.clear()


# ===========================================================================
# _make_authenticated_tmdb_api_request
# ===========================================================================

class TestMakeAuthenticatedTMDBApiRequest(TMDBTestBase):

    @patch('services.tmdbAPIService.make_request')
    def test_builds_url_from_env_base_url(self, mock_make_request):
        mock_make_request.return_value = MagicMock()
        with patch.dict(os.environ, {'TMDB_API_KEY': 'test-key', 'TMDB_URL': 'https://custom.tmdb.host/3'}):
            _make_authenticated_tmdb_api_request('genre/tv/list')
        mock_make_request.assert_called_once()
        args = mock_make_request.call_args[0]
        self.assertEqual(args[0], 'https://custom.tmdb.host/3/genre/tv/list')

    @patch('services.tmdbAPIService.make_request')
    def test_falls_back_to_default_base_url(self, mock_make_request):
        mock_make_request.return_value = MagicMock()
        env = {'TMDB_API_KEY': 'test-key'}
        env.pop('TMDB_URL', None)
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop('TMDB_URL', None)
            _make_authenticated_tmdb_api_request('genre/tv/list')
        args = mock_make_request.call_args[0]
        self.assertIn('api.themoviedb.org/3', args[0])

    @patch('services.tmdbAPIService.make_request')
    def test_injects_bearer_token_header(self, mock_make_request):
        mock_make_request.return_value = MagicMock()
        with patch.dict(os.environ, {'TMDB_API_KEY': 'super-secret'}):
            _make_authenticated_tmdb_api_request('genre/tv/list')
        _, kwargs = mock_make_request.call_args
        # headers may be positional or keyword depending on make_request signature
        call_args = mock_make_request.call_args
        # headers are passed as the 5th positional arg (index 4)
        headers = call_args[0][4] if len(call_args[0]) > 4 else call_args[1].get('headers', {})
        self.assertEqual(headers.get('Authorization'), 'Bearer super-secret')

    @patch('services.tmdbAPIService.make_request')
    def test_merges_extra_headers(self, mock_make_request):
        mock_make_request.return_value = MagicMock()
        with patch.dict(os.environ, {'TMDB_API_KEY': 'key'}):
            _make_authenticated_tmdb_api_request('some/path', headers={'X-Custom': 'value'})
        call_args = mock_make_request.call_args
        headers = call_args[0][4] if len(call_args[0]) > 4 else call_args[1].get('headers', {})
        self.assertEqual(headers.get('X-Custom'), 'value')
        self.assertIn('Authorization', headers)

    @patch('services.tmdbAPIService.make_request')
    def test_passes_params_and_body(self, mock_make_request):
        mock_make_request.return_value = MagicMock()
        with patch.dict(os.environ, {'TMDB_API_KEY': 'key'}):
            _make_authenticated_tmdb_api_request('path', params={'p': 1}, body={'b': 2})
        call_args = mock_make_request.call_args[0]
        self.assertEqual(call_args[2], {'p': 1})
        self.assertEqual(call_args[3], {'b': 2})


# ===========================================================================
# get_tv_genres
# ===========================================================================

class TestGetTVGenres(TMDBTestBase):

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_returns_genres_with_lowercased_names(self, mock_req):
        mock_req.return_value = _make_mock_response({
            'genres': [
                {'id': 1, 'name': 'Action'},
                {'id': 2, 'name': 'Comedy'},
            ]
        })
        genres = get_tv_genres()
        self.assertEqual(genres, [{'id': 1, 'name': 'action'}, {'id': 2, 'name': 'comedy'}])

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_calls_correct_endpoint(self, mock_req):
        mock_req.return_value = _make_mock_response({'genres': []})
        get_tv_genres()
        mock_req.assert_called_once_with('genre/tv/list')

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_result_is_cached_on_second_call(self, mock_req):
        mock_req.return_value = _make_mock_response({'genres': [{'id': 1, 'name': 'Drama'}]})
        get_tv_genres()
        get_tv_genres()
        # Second call should hit the cache — API called only once.
        mock_req.assert_called_once()

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_returns_empty_list_when_genres_missing(self, mock_req):
        mock_req.return_value = _make_mock_response({})
        # get('genres') returns None; the list comprehension will raise — this
        # documents current behaviour and guards against silent regressions.
        with self.assertRaises(TypeError):
            get_tv_genres()


# ===========================================================================
# get_movie_genres
# ===========================================================================

class TestGetMovieGenres(TMDBTestBase):

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_returns_genres_with_lowercased_names(self, mock_req):
        mock_req.return_value = _make_mock_response({
            'genres': [
                {'id': 28, 'name': 'Action'},
                {'id': 35, 'name': 'Comedy'},
            ]
        })
        genres = get_movie_genres()
        self.assertEqual(genres, [{'id': 28, 'name': 'action'}, {'id': 35, 'name': 'comedy'}])

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_calls_correct_endpoint(self, mock_req):
        mock_req.return_value = _make_mock_response({'genres': []})
        get_movie_genres()
        mock_req.assert_called_once_with('genre/movie/list')

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_result_is_cached_on_second_call(self, mock_req):
        mock_req.return_value = _make_mock_response({'genres': [{'id': 28, 'name': 'Action'}]})
        get_movie_genres()
        get_movie_genres()
        mock_req.assert_called_once()

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_tv_and_movie_caches_are_independent(self, mock_req):
        mock_req.return_value = _make_mock_response({'genres': [{'id': 1, 'name': 'X'}]})
        get_tv_genres()
        get_movie_genres()
        # Each endpoint should have been called exactly once (not sharing cache keys).
        self.assertEqual(mock_req.call_count, 2)


# ===========================================================================
# get_recommendations_by_id
# ===========================================================================

class TestGetRecommendationsByID(TMDBTestBase):

    def _mock_page(self, items):
        return _make_mock_response({'results': items})

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_raises_on_invalid_type(self, mock_req):
        with self.assertRaises(Exception) as ctx:
            get_recommendations_by_id('anime', '123')
        self.assertIn('movie, tv', str(ctx.exception))

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_raises_when_id_missing(self, mock_req):
        with self.assertRaises(Exception) as ctx:
            get_recommendations_by_id('tv', '')
        self.assertIn('ID is required', str(ctx.exception))

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_fetches_correct_number_of_pages(self, mock_req):
        mock_req.return_value = self._mock_page([_make_reco()])
        get_recommendations_by_id('tv', '42', pages=3)
        self.assertEqual(mock_req.call_count, 3)

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_uses_correct_endpoint_for_tv(self, mock_req):
        mock_req.return_value = self._mock_page([])
        get_recommendations_by_id('tv', '99', pages=1)
        url = mock_req.call_args[0][0]
        self.assertEqual(url, 'tv/99/recommendations')

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_uses_correct_endpoint_for_movie(self, mock_req):
        mock_req.return_value = self._mock_page([])
        get_recommendations_by_id('movie', '77', pages=1)
        url = mock_req.call_args[0][0]
        self.assertEqual(url, 'movie/77/recommendations')

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_results_sorted_by_vote_average_desc_by_default(self, mock_req):
        recos = [_make_reco(id=i, vote_average=float(i)) for i in range(1, 4)]
        mock_req.return_value = self._mock_page(recos)
        result = get_recommendations_by_id('tv', '1', pages=1)
        averages = [r['vote_average'] for r in result]
        self.assertEqual(averages, sorted(averages, reverse=True))

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_results_sorted_asc_when_requested(self, mock_req):
        recos = [_make_reco(id=i, vote_average=float(i)) for i in range(1, 4)]
        mock_req.return_value = self._mock_page(recos)
        result = get_recommendations_by_id('tv', '2', pages=1, sort_dir='asc')
        averages = [r['vote_average'] for r in result]
        self.assertEqual(averages, sorted(averages))

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_filters_below_min_vote_count(self, mock_req):
        recos = [
            _make_reco(id=1, vote_count=5),   # below default threshold of 10
            _make_reco(id=2, vote_count=50),
        ]
        mock_req.return_value = self._mock_page(recos)
        result = get_recommendations_by_id('tv', '3', pages=1, min_vote_count=10)
        ids = [r['id'] for r in result]
        self.assertNotIn(1, ids)
        self.assertIn(2, ids)

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_enforce_orig_language_filters_non_matching(self, mock_req):
        recos = [
            _make_reco(id=1, original_language='en'),
            _make_reco(id=2, original_language='fr'),
        ]
        mock_req.return_value = self._mock_page(recos)
        env = {'LANGUAGE': 'en-US', 'ENFORCE_ORIG_LANGUAGE': 'true'}
        with patch.dict(os.environ, env):
            result = get_recommendations_by_id('tv', '4', pages=1)
        ids = [r['id'] for r in result]
        self.assertIn(1, ids)
        self.assertNotIn(2, ids)

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_enforce_orig_language_false_keeps_all(self, mock_req):
        recos = [
            _make_reco(id=1, original_language='en'),
            _make_reco(id=2, original_language='ja'),
        ]
        mock_req.return_value = self._mock_page(recos)
        env = {'LANGUAGE': 'en-US', 'ENFORCE_ORIG_LANGUAGE': 'false'}
        with patch.dict(os.environ, env):
            result = get_recommendations_by_id('tv', '5', pages=1)
        self.assertEqual(len(result), 2)

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_result_is_cached_for_same_args(self, mock_req):
        mock_req.return_value = self._mock_page([_make_reco()])
        get_recommendations_by_id('tv', '6', pages=1)
        get_recommendations_by_id('tv', '6', pages=1)
        mock_req.assert_called_once()

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_different_ids_use_separate_cache_entries(self, mock_req):
        mock_req.return_value = self._mock_page([_make_reco()])
        get_recommendations_by_id('tv', '7', pages=1)
        get_recommendations_by_id('tv', '8', pages=1)
        self.assertEqual(mock_req.call_count, 2)

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_passes_language_param(self, mock_req):
        mock_req.return_value = self._mock_page([])
        with patch.dict(os.environ, {'LANGUAGE': 'fr-FR'}):
            get_recommendations_by_id('movie', '10', pages=1)
        params = mock_req.call_args[1].get('params') or mock_req.call_args[0][1]
        self.assertEqual(params.get('language'), 'fr-FR')

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_sorts_by_custom_sort_by_key(self, mock_req):
        recos = [
            _make_reco(id=1, vote_count=30),
            _make_reco(id=2, vote_count=10),
            _make_reco(id=3, vote_count=20),
        ]
        mock_req.return_value = self._mock_page(recos)
        result = get_recommendations_by_id('tv', '11', pages=1, sort_by='vote_count', min_vote_count=0)
        counts = [r['vote_count'] for r in result]
        self.assertEqual(counts, sorted(counts, reverse=True))

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_passes_incrementing_page_param_per_page(self, mock_req):
        mock_req.return_value = self._mock_page([])
        get_recommendations_by_id('tv', '12', pages=2)
        pages = [
            (c[1].get('params') or c[0][1]).get('page')
            for c in mock_req.call_args_list
        ]
        self.assertEqual(pages, [1, 2])

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_raises_type_error_when_results_missing(self, mock_req):
        # .get("results") yields None; extending with None raises TypeError.
        mock_req.return_value = _make_mock_response({})
        with self.assertRaises(TypeError):
            get_recommendations_by_id('tv', '13', pages=1)


# ===========================================================================
# get_popular_series
# ===========================================================================

class TestGetPopularSeries(TMDBTestBase):

    def _page_response(self, items):
        return _make_mock_response({'results': items})

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_returns_up_to_popular_series_count(self, mock_req):
        # 20 items per page; default count is 100 → need 5 pages
        page_items = [_make_reco(id=i) for i in range(20)]
        mock_req.return_value = self._page_response(page_items)
        env = {'POPULAR_SERIES_COUNT': '40'}
        with patch.dict(os.environ, env):
            result = get_popular_series()
        self.assertEqual(len(result), 40)

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_calls_correct_endpoint(self, mock_req):
        mock_req.return_value = self._page_response([_make_reco()] * 20)
        with patch.dict(os.environ, {'POPULAR_SERIES_COUNT': '20'}):
            get_popular_series()
        url = mock_req.call_args[0][0]
        self.assertEqual(url, 'tv/popular')

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_stops_early_when_api_returns_empty_results(self, mock_req):
        # First page has items; second page has none → should stop.
        mock_req.side_effect = [
            self._page_response([_make_reco(id=i) for i in range(5)]),
            self._page_response([]),
        ]
        with patch.dict(os.environ, {'POPULAR_SERIES_COUNT': '100'}):
            result = get_popular_series()
        self.assertEqual(len(result), 5)

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_stops_early_when_api_returns_none_results(self, mock_req):
        mock_req.return_value = _make_mock_response({'results': None})
        with patch.dict(os.environ, {'POPULAR_SERIES_COUNT': '100'}):
            result = get_popular_series()
        self.assertEqual(result, [])

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_excludes_ids_in_exclusion_list(self, mock_req):
        items = [_make_reco(id=i) for i in range(1, 6)]
        mock_req.return_value = self._page_response(items)
        with patch.dict(os.environ, {'POPULAR_SERIES_COUNT': '5'}):
            result = get_popular_series(excluded_tmdb_ids=[2, 4])
        ids = [r['id'] for r in result]
        self.assertNotIn(2, ids)
        self.assertNotIn(4, ids)

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_no_exclusion_returns_all_items(self, mock_req):
        items = [_make_reco(id=i) for i in range(1, 6)]
        mock_req.return_value = self._page_response(items)
        with patch.dict(os.environ, {'POPULAR_SERIES_COUNT': '5'}):
            result = get_popular_series()
        self.assertEqual(len(result), 5)

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_enforce_orig_language_filters_series(self, mock_req):
        items = [
            _make_reco(id=1, original_language='en'),
            _make_reco(id=2, original_language='ko'),
        ] * 10
        mock_req.return_value = self._page_response(items)
        env = {'LANGUAGE': 'en-US', 'ENFORCE_ORIG_LANGUAGE': 'true', 'POPULAR_SERIES_COUNT': '5'}
        with patch.dict(os.environ, env):
            result = get_popular_series()
        langs = {r['original_language'] for r in result}
        self.assertEqual(langs, {'en'})

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_result_is_cached(self, mock_req):
        mock_req.return_value = self._page_response([_make_reco()] * 20)
        with patch.dict(os.environ, {'POPULAR_SERIES_COUNT': '20'}):
            get_popular_series()
            get_popular_series()
        # Cache key does not include excluded_tmdb_ids; second call hits cache.
        mock_req.assert_called_once()

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_passes_language_param(self, mock_req):
        mock_req.return_value = self._page_response([_make_reco()] * 20)
        with patch.dict(os.environ, {'POPULAR_SERIES_COUNT': '20', 'LANGUAGE': 'de-DE'}):
            get_popular_series()
        params = mock_req.call_args[1].get('params') or mock_req.call_args[0][1]
        self.assertEqual(params.get('language'), 'de-DE')


# ===========================================================================
# get_popular_movies
# ===========================================================================

class TestGetPopularMovies(TMDBTestBase):

    def _page_response(self, items):
        return _make_mock_response({'results': items})

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_returns_up_to_popular_movies_count(self, mock_req):
        page_items = [_make_reco(id=i) for i in range(20)]
        mock_req.return_value = self._page_response(page_items)
        with patch.dict(os.environ, {'POPULAR_MOVIES_COUNT': '40'}):
            result = get_popular_movies()
        self.assertEqual(len(result), 40)

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_calls_correct_endpoint(self, mock_req):
        mock_req.return_value = self._page_response([_make_reco()] * 20)
        with patch.dict(os.environ, {'POPULAR_MOVIES_COUNT': '20'}):
            get_popular_movies()
        url = mock_req.call_args[0][0]
        self.assertEqual(url, 'movie/popular')

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_stops_early_when_api_returns_empty_results(self, mock_req):
        mock_req.side_effect = [
            self._page_response([_make_reco(id=i) for i in range(3)]),
            self._page_response([]),
        ]
        with patch.dict(os.environ, {'POPULAR_MOVIES_COUNT': '100'}):
            result = get_popular_movies()
        self.assertEqual(len(result), 3)

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_stops_early_when_api_returns_none_results(self, mock_req):
        mock_req.return_value = _make_mock_response({'results': None})
        with patch.dict(os.environ, {'POPULAR_MOVIES_COUNT': '100'}):
            result = get_popular_movies()
        self.assertEqual(result, [])

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_excludes_ids_in_exclusion_list(self, mock_req):
        items = [_make_reco(id=i) for i in range(1, 6)]
        mock_req.return_value = self._page_response(items)
        with patch.dict(os.environ, {'POPULAR_MOVIES_COUNT': '5'}):
            result = get_popular_movies(excluded_tmdb_ids=[1, 3])
        ids = [r['id'] for r in result]
        self.assertNotIn(1, ids)
        self.assertNotIn(3, ids)

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_enforce_orig_language_filters_movies(self, mock_req):
        items = [
            _make_reco(id=1, original_language='en'),
            _make_reco(id=2, original_language='es'),
        ] * 10
        mock_req.return_value = self._page_response(items)
        env = {'LANGUAGE': 'en-US', 'ENFORCE_ORIG_LANGUAGE': 'true', 'POPULAR_MOVIES_COUNT': '5'}
        with patch.dict(os.environ, env):
            result = get_popular_movies()
        langs = {r['original_language'] for r in result}
        self.assertEqual(langs, {'en'})

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_result_is_cached(self, mock_req):
        mock_req.return_value = self._page_response([_make_reco()] * 20)
        with patch.dict(os.environ, {'POPULAR_MOVIES_COUNT': '20'}):
            get_popular_movies()
            get_popular_movies()
        mock_req.assert_called_once()

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_passes_language_param(self, mock_req):
        mock_req.return_value = self._page_response([_make_reco()] * 20)
        with patch.dict(os.environ, {'POPULAR_MOVIES_COUNT': '20', 'LANGUAGE': 'ja-JP'}):
            get_popular_movies()
        params = mock_req.call_args[1].get('params') or mock_req.call_args[0][1]
        self.assertEqual(params.get('language'), 'ja-JP')


# ===========================================================================
# get_upcoming_movies
# ===========================================================================

class TestGetUpcomingMovies(TMDBTestBase):

    def _page_response(self, items):
        return _make_mock_response({'results': items})

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_returns_up_to_upcoming_movies_count(self, mock_req):
        page_items = [_make_reco(id=i) for i in range(20)]
        mock_req.return_value = self._page_response(page_items)
        with patch.dict(os.environ, {'UPCOMING_MOVIES_COUNT': '40'}):
            result = get_upcoming_movies()
        self.assertEqual(len(result), 40)

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_calls_correct_endpoint(self, mock_req):
        mock_req.return_value = self._page_response([_make_reco()] * 20)
        with patch.dict(os.environ, {'UPCOMING_MOVIES_COUNT': '20'}):
            get_upcoming_movies()
        url = mock_req.call_args[0][0]
        self.assertEqual(url, 'movie/upcoming')

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_stops_early_when_api_returns_empty_results(self, mock_req):
        mock_req.side_effect = [
            self._page_response([_make_reco(id=i) for i in range(3)]),
            self._page_response([]),
        ]
        with patch.dict(os.environ, {'UPCOMING_MOVIES_COUNT': '100'}):
            result = get_upcoming_movies()
        self.assertEqual(len(result), 3)

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_stops_early_when_api_returns_none_results(self, mock_req):
        mock_req.return_value = _make_mock_response({'results': None})
        with patch.dict(os.environ, {'UPCOMING_MOVIES_COUNT': '100'}):
            result = get_upcoming_movies()
        self.assertEqual(result, [])

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_excludes_ids_in_exclusion_list(self, mock_req):
        items = [_make_reco(id=i) for i in range(1, 6)]
        mock_req.return_value = self._page_response(items)
        with patch.dict(os.environ, {'UPCOMING_MOVIES_COUNT': '5'}):
            result = get_upcoming_movies(excluded_tmdb_ids=[2, 5])
        ids = [r['id'] for r in result]
        self.assertNotIn(2, ids)
        self.assertNotIn(5, ids)

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_enforce_orig_language_filters_upcoming(self, mock_req):
        items = [
            _make_reco(id=1, original_language='en'),
            _make_reco(id=2, original_language='pt'),
        ] * 10
        mock_req.return_value = self._page_response(items)
        env = {'LANGUAGE': 'en-US', 'ENFORCE_ORIG_LANGUAGE': 'true', 'UPCOMING_MOVIES_COUNT': '5'}
        with patch.dict(os.environ, env):
            result = get_upcoming_movies()
        langs = {r['original_language'] for r in result}
        self.assertEqual(langs, {'en'})

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_result_is_cached(self, mock_req):
        mock_req.return_value = self._page_response([_make_reco()] * 20)
        with patch.dict(os.environ, {'UPCOMING_MOVIES_COUNT': '20'}):
            get_upcoming_movies()
            get_upcoming_movies()
        mock_req.assert_called_once()

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_passes_language_param(self, mock_req):
        mock_req.return_value = self._page_response([_make_reco()] * 20)
        with patch.dict(os.environ, {'UPCOMING_MOVIES_COUNT': '20', 'LANGUAGE': 'es-ES'}):
            get_upcoming_movies()
        params = mock_req.call_args[1].get('params') or mock_req.call_args[0][1]
        self.assertEqual(params.get('language'), 'es-ES')

    @patch('services.tmdbAPIService._make_authenticated_tmdb_api_request')
    def test_no_exclusion_returns_all_items(self, mock_req):
        items = [_make_reco(id=i) for i in range(1, 6)]
        mock_req.return_value = self._page_response(items)
        with patch.dict(os.environ, {'UPCOMING_MOVIES_COUNT': '5'}):
            result = get_upcoming_movies()
        self.assertEqual(len(result), 5)


if __name__ == '__main__':
    unittest.main()

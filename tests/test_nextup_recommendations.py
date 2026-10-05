import unittest
from unittest.mock import patch, MagicMock
import os

import NextUp
from services.watchstateAPIService import Series


def _reco(id: int, genres=None):
    # Minimal TMDB-recommendation-shaped dict used by the exclusion filter.
    return {'id': id, 'name': f'Show {id}', 'genre_ids': genres or []}


class TestGenerateSeriesRecommendationsExclusion(unittest.TestCase):
    """Regression tests for the watched-series exclusion.

    A series present in the user's watch history (whether truly played or just
    marked watched) must never appear in that user's saved recommendations.
    The bug was an int/str mismatch: available-library and TMDB recommendation
    ids are ints, but watched tmdb_ids arrive as strings, so the membership
    check never excluded them.
    """

    def setUp(self):
        self.user = {'Id': 'a' * 32, 'Name': 'alice'}
        # Ensure WatchState branch isn't taken via real env.
        self._env = patch.dict(os.environ, {}, clear=False)
        self._env.start()

    def tearDown(self):
        self._env.stop()

    def _run(self, available_ids, watched_series, recos_by_seed):
        """Invoke generate_series_recommendations with all collaborators mocked.

        Returns the list of reco ids that were written to the filesystem.
        """
        captured = {}

        def fake_write(base_path, metadata_json, type):
            captured['metadata'] = metadata_json

        with patch.object(NextUp.jellyfin_api_service, 'get_all_available_series', return_value=available_ids), \
             patch.object(NextUp, 'get_all_user_watched_series', return_value=watched_series), \
             patch.object(NextUp.tmdb_api_service, 'get_recommendations_by_id', side_effect=lambda type, id, **kw: recos_by_seed.get(str(id), [])), \
             patch.object(NextUp, 'weight_series_recos_by_watched_genres', side_effect=lambda watched, recos: recos), \
             patch.object(NextUp.jellyfin_adapter, 'convert_series_reco_to_metadata', side_effect=lambda reco: reco), \
             patch.object(NextUp, 'write_recos_to_filesystem', side_effect=fake_write):
            NextUp.generate_series_recommendations(
                self.user,
                max_days_lookback=365,
                max_recos=20,
                min_episode_watch_count=1,
                max_total_recos=None,
            )

        written = captured.get('metadata', [])
        return [r['id'] for r in written]

    def test_watched_series_not_recommended_even_when_tmdb_recommends_it(self):
        # User watched series 63404 (tmdb_id arrives as a STRING from history).
        watched = [Series(name='Taskmaster', id='show-1', genres=['comedy'], tmdb_id='63404')]
        # 63404 is NOT in the available library, so only the watched list can
        # exclude it. TMDB recommends 63404 (already watched) plus a new show.
        available = [100, 200]
        recos = {'63404': [_reco(63404), _reco(999)]}

        written_ids = self._run(available, watched, recos)

        self.assertNotIn(63404, written_ids, "already-watched series leaked into recommendations")
        self.assertIn(999, written_ids, "a genuinely new recommendation should still be included")

    def test_available_series_still_excluded(self):
        # A series already on the server (int id) must also stay excluded.
        watched = [Series(name='Seed', id='show-2', genres=[], tmdb_id='555')]
        available = [100, 200]
        recos = {'555': [_reco(100), _reco(777)]}

        written_ids = self._run(available, watched, recos)

        self.assertNotIn(100, written_ids)
        self.assertIn(777, written_ids)

    def test_no_watched_series_writes_empty(self):
        captured = {}

        def fake_write(base_path, metadata_json, type):
            captured['metadata'] = metadata_json

        with patch.object(NextUp.jellyfin_api_service, 'get_all_available_series', return_value=[1, 2]), \
             patch.object(NextUp, 'get_all_user_watched_series', return_value=None), \
             patch.object(NextUp, 'write_recos_to_filesystem', side_effect=fake_write):
            NextUp.generate_series_recommendations(
                self.user, max_days_lookback=1, max_recos=10,
                min_episode_watch_count=1, max_total_recos=None,
            )

        self.assertEqual(captured.get('metadata'), [])


if __name__ == '__main__':
    unittest.main()

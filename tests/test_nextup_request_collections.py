import unittest
from unittest.mock import patch, MagicMock
import os

import NextUp


def _item(item_id: str) -> dict:
    return {'Id': item_id}


class TestGenerateRequestCollectionForUser(unittest.TestCase):
    def setUp(self):
        self.user = {'Id': 'a' * 32, 'Name': 'alice'}

    def test_skipped_when_no_seerr_identity(self):
        with patch.object(NextUp.seerr_api_service, 'get_user_by_jellyfin_id', return_value=None), \
             patch.object(NextUp.seerr_api_service, 'get_requests') as mock_requests, \
             patch.object(NextUp.jellyfin_api_service, 'create_collection') as mock_create, \
             patch.object(NextUp.jellyfin_api_service, 'get_collection_by_name') as mock_by_name:
            NextUp.generate_request_collection_for_user(self.user)

        mock_requests.assert_not_called()
        mock_create.assert_not_called()
        mock_by_name.assert_not_called()

    def test_creates_collection_seeded_with_resolved_ids_when_none_exists(self):
        requests_list = [
            {'media': {'tmdbId': 111}},
            {'media': {'tmdbId': 222}},
        ]

        def fake_resolve(ids, item_type):
            if item_type == 'Movie':
                return [_item('movie-1')]
            return [_item('series-1')]

        with patch.object(NextUp.seerr_api_service, 'get_user_by_jellyfin_id', return_value={'id': 7}), \
             patch.object(NextUp.seerr_api_service, 'get_requests', return_value=requests_list), \
             patch.object(NextUp.jellyfin_api_service, 'get_items_by_tmdb_ids', side_effect=fake_resolve), \
             patch.object(NextUp.jellyfin_api_service, 'get_collection_by_name', return_value=None), \
             patch.object(NextUp.jellyfin_api_service, 'create_collection') as mock_create, \
             patch.object(NextUp.jellyfin_api_service, 'add_items_to_collection') as mock_add:
            NextUp.generate_request_collection_for_user(self.user)

        mock_create.assert_called_once()
        name_arg, ids_arg = mock_create.call_args[0]
        self.assertEqual(name_arg, 'Requests - alice')
        self.assertEqual(set(ids_arg), {'movie-1', 'series-1'})
        mock_add.assert_not_called()

    def test_delta_adds_missing_and_removes_stale(self):
        requests_list = [{'media': {'tmdbId': 111}}, {'media': {'tmdbId': 222}}]

        def fake_resolve(ids, item_type):
            # Desired set: keep-1 and new-1.
            if item_type == 'Movie':
                return [_item('keep-1'), _item('new-1')]
            return []

        collection = {'Id': 'c1', 'Name': 'Requests - alice'}
        # Current contents: keep-1 (stays) and stale-1 (should be removed).
        current = [_item('keep-1'), _item('stale-1')]

        with patch.object(NextUp.seerr_api_service, 'get_user_by_jellyfin_id', return_value={'id': 7}), \
             patch.object(NextUp.seerr_api_service, 'get_requests', return_value=requests_list), \
             patch.object(NextUp.jellyfin_api_service, 'get_items_by_tmdb_ids', side_effect=fake_resolve), \
             patch.object(NextUp.jellyfin_api_service, 'get_collection_by_name', return_value=collection), \
             patch.object(NextUp.jellyfin_api_service, 'get_collection_items', return_value=current), \
             patch.object(NextUp.jellyfin_api_service, 'add_items_to_collection') as mock_add, \
             patch.object(NextUp.jellyfin_api_service, 'remove_items_from_collection') as mock_remove:
            NextUp.generate_request_collection_for_user(self.user)

        add_id, add_list = mock_add.call_args[0]
        remove_id, remove_list = mock_remove.call_args[0]
        self.assertEqual(add_id, 'c1')
        self.assertEqual(set(add_list), {'new-1'})
        self.assertEqual(remove_id, 'c1')
        self.assertEqual(set(remove_list), {'stale-1'})

    def test_no_create_when_nothing_on_server(self):
        requests_list = [{'media': {'tmdbId': 111}}]

        with patch.object(NextUp.seerr_api_service, 'get_user_by_jellyfin_id', return_value={'id': 7}), \
             patch.object(NextUp.seerr_api_service, 'get_requests', return_value=requests_list), \
             patch.object(NextUp.jellyfin_api_service, 'get_items_by_tmdb_ids', return_value=[]), \
             patch.object(NextUp.jellyfin_api_service, 'get_collection_by_name', return_value=None), \
             patch.object(NextUp.jellyfin_api_service, 'create_collection') as mock_create:
            NextUp.generate_request_collection_for_user(self.user)

        mock_create.assert_not_called()


class TestNextUpGating(unittest.TestCase):
    """The gating flag path in NextUp(). Request collections run inside the
    per-user loop; all heavier generation is disabled/stubbed."""

    def _run_nextup(self, env, users=None):
        users = users or [{'Id': 'a' * 32, 'Name': 'alice'}]
        base_env = {
            'GENERATE_RECOS_FOR': ','.join(u['Name'] for u in users),
            'DISABLE_MOVIE_RECOMMENDATIONS': 'true',
            'DISABLE_SERIES_RECOMMENDATIONS': 'true',
            'INCLUDE_UPCOMING_MOVIE_RECOMMENDATIONS': 'false',
            'INCLUDE_POPULAR_MOVIE_RECOMMENDATIONS': 'false',
            'INCLUDE_POPULAR_SERIES_RECOMMENDATIONS': 'false',
            'MIN_MOVIE_WATCH_PERCENT': '0',
            'MAX_MOVIE_DAYS_LOOKBACK': '0',
            'MAX_TOTAL_MOVIE_RECOMMENDATIONS': '0',
            'MAX_SERIES_DAYS_LOOKBACK': '0',
            'MAX_TOTAL_SERIES_RECOMMENDATIONS': '0',
        }
        base_env.update(env)

        with patch.dict(os.environ, base_env, clear=True), \
             patch.object(NextUp.jellyfin_api_service, 'get_users', return_value=users), \
             patch.object(NextUp, 'create_reco_dir'), \
             patch.object(NextUp, 'generate_request_collection_for_user') as mock_gen:
            NextUp.NextUp()
        return mock_gen

    def test_not_called_when_flag_off(self):
        mock_gen = self._run_nextup({'GENERATE_REQUEST_COLLECTIONS': 'false'})
        mock_gen.assert_not_called()

    def test_not_called_when_seerr_not_configured(self):
        mock_gen = self._run_nextup({'GENERATE_REQUEST_COLLECTIONS': 'true'})
        mock_gen.assert_not_called()

    def test_called_once_per_user_when_flag_on_and_seerr_configured(self):
        users = [{'Id': 'a' * 32, 'Name': 'alice'}, {'Id': 'b' * 32, 'Name': 'bob'}]
        mock_gen = self._run_nextup({
            'GENERATE_REQUEST_COLLECTIONS': 'true',
            'SEERR_URL': 'http://seerr',
            'SEERR_API_KEY': 'key',
        }, users=users)
        self.assertEqual(mock_gen.call_count, 2)
        called_names = {call.args[0]['Name'] for call in mock_gen.call_args_list}
        self.assertEqual(called_names, {'alice', 'bob'})


if __name__ == '__main__':
    unittest.main()

import unittest
import uuid

from utils.helpers import (
    is_valid_uuid,
    convert_string_to_uuid,
    parse_jellyfin_date,
    create_map_by_id,
    safe_call,
)


# ===========================================================================
# is_valid_uuid
# ===========================================================================

class TestIsValidUuid(unittest.TestCase):

    def test_returns_true_for_canonical_uuid(self):
        valid = str(uuid.uuid4())
        self.assertTrue(is_valid_uuid(valid))

    def test_returns_false_for_non_uuid_string(self):
        self.assertFalse(is_valid_uuid('12345'))

    def test_returns_false_for_empty_string(self):
        self.assertFalse(is_valid_uuid(''))

    def test_returns_true_for_uppercase_uuid(self):
        # UUID comparison is done case-insensitively via .lower().
        valid_upper = str(uuid.uuid4()).upper()
        self.assertTrue(is_valid_uuid(valid_upper))

    def test_returns_false_for_32_char_hex_without_dashes(self):
        # A dashless 32-char hex parses as a UUID but its canonical string has
        # dashes, so the equality check fails.
        hex32 = uuid.uuid4().hex  # 32 chars, no dashes
        self.assertFalse(is_valid_uuid(hex32))


# ===========================================================================
# convert_string_to_uuid
# ===========================================================================

class TestConvertStringToUuid(unittest.TestCase):

    def test_inserts_dashes_into_32_char_hex(self):
        raw = 'a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6'
        result = convert_string_to_uuid(raw)
        self.assertEqual(result, 'a1b2c3d4-e5f6-a7b8-c9d0-e1f2a3b4c5d6')

    def test_returns_unchanged_when_already_canonical_uuid(self):
        canonical = str(uuid.uuid4())
        # Strip dashes to feed a 32-char string that is a valid dashless uuid;
        # function returns the inserted-dash form.
        result = convert_string_to_uuid(canonical.replace('-', ''))
        self.assertEqual(result, canonical)

    def test_raises_for_wrong_length(self):
        with self.assertRaises(Exception) as ctx:
            convert_string_to_uuid('tooshort')
        self.assertIn('UUID format', str(ctx.exception))

    def test_raises_for_empty_string(self):
        with self.assertRaises(Exception):
            convert_string_to_uuid('')

    def test_raises_for_none(self):
        with self.assertRaises(Exception):
            convert_string_to_uuid(None)


# ===========================================================================
# parse_jellyfin_date
# ===========================================================================

class TestParseJellyfinDate(unittest.TestCase):

    def test_extracts_date_portion_before_t(self):
        self.assertEqual(parse_jellyfin_date('2026-01-15T10:30:00.000Z'), '2026-01-15')

    def test_returns_whole_string_when_no_t(self):
        self.assertEqual(parse_jellyfin_date('2026-01-15'), '2026-01-15')

    def test_returns_none_for_empty_string(self):
        self.assertIsNone(parse_jellyfin_date(''))

    def test_returns_none_for_none(self):
        self.assertIsNone(parse_jellyfin_date(None))


# ===========================================================================
# create_map_by_id
# ===========================================================================

class TestCreateMapById(unittest.TestCase):

    def test_builds_map_keyed_by_id_field(self):
        items = [{'id': 'a', 'v': 1}, {'id': 'b', 'v': 2}]
        result = create_map_by_id(items, 'id')
        self.assertEqual(result, {'a': {'id': 'a', 'v': 1}, 'b': {'id': 'b', 'v': 2}})

    def test_returns_empty_map_for_empty_list(self):
        self.assertEqual(create_map_by_id([], 'id'), {})

    def test_later_item_wins_on_duplicate_key(self):
        items = [{'id': 'x', 'v': 1}, {'id': 'x', 'v': 2}]
        result = create_map_by_id(items, 'id')
        self.assertEqual(result['x']['v'], 2)

    def test_supports_custom_key_field(self):
        items = [{'name': 'foo'}, {'name': 'bar'}]
        result = create_map_by_id(items, 'name')
        self.assertIn('foo', result)
        self.assertIn('bar', result)


# ===========================================================================
# safe_call
# ===========================================================================

class TestSafeCall(unittest.TestCase):

    def test_returns_function_result_on_success(self):
        self.assertEqual(safe_call(lambda x: x * 2, 5), 10)

    def test_passes_args_and_kwargs(self):
        def fn(a, b, c=0):
            return a + b + c
        self.assertEqual(safe_call(fn, 1, 2, c=3), 6)

    def test_returns_none_on_exception(self):
        def boom():
            raise ValueError('kaboom')
        self.assertIsNone(safe_call(boom))

    def test_does_not_propagate_exception(self):
        def boom():
            raise RuntimeError('nope')
        # Should not raise.
        result = safe_call(boom)
        self.assertIsNone(result)


if __name__ == '__main__':
    unittest.main()

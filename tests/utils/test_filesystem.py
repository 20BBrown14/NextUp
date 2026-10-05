import unittest
from unittest.mock import patch, MagicMock
import os
import tempfile
from pathlib import Path

from utils.filesystem import (
    create_directory,
    save_json,
    read_json,
    create_hard_link,
    copy_file,
    get_all_dirs_in_dir,
    recursively_rm_dir,
    does_path_exist,
)


class FilesystemTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def path(self, *parts):
        return os.path.join(self.tmp, *parts)


# ===========================================================================
# create_directory
# ===========================================================================

class TestCreateDirectory(FilesystemTestBase):

    def test_creates_directory(self):
        target = self.path('new_dir')
        result = create_directory(target)
        self.assertTrue(os.path.isdir(target))
        self.assertEqual(result, Path(target).resolve())

    def test_creates_nested_parents(self):
        target = self.path('a', 'b', 'c')
        create_directory(target)
        self.assertTrue(os.path.isdir(target))

    def test_does_not_raise_if_exists(self):
        target = self.path('existing')
        create_directory(target)
        # Second call must not raise.
        create_directory(target)
        self.assertTrue(os.path.isdir(target))

    def test_accepts_path_object(self):
        target = Path(self.path('from_path_obj'))
        create_directory(target)
        self.assertTrue(target.is_dir())


# ===========================================================================
# save_json / read_json
# ===========================================================================

class TestSaveAndReadJson(FilesystemTestBase):

    def test_save_then_read_round_trip(self):
        fp = self.path('data.json')
        data = {'name': 'test', 'values': [1, 2, 3]}
        save_json(fp, data)
        self.assertEqual(read_json(fp), data)

    def test_save_json_preserves_unicode(self):
        fp = self.path('unicode.json')
        data = {'title': 'Pokémon ★'}
        save_json(fp, data)
        self.assertEqual(read_json(fp), data)

    @patch('utils.filesystem.logger')
    def test_save_json_logs_error_on_failure(self, mock_logger):
        # Writing to a path whose parent doesn't exist raises inside save_json,
        # which is caught and logged rather than propagated.
        fp = self.path('missing_dir', 'data.json')
        save_json(fp, {'a': 1})
        mock_logger.error.assert_called_once()

    @patch('utils.filesystem.logger')
    def test_read_json_returns_none_for_missing_file(self, mock_logger):
        result = read_json(self.path('does_not_exist.json'))
        self.assertIsNone(result)
        mock_logger.error.assert_called_once()

    @patch('utils.filesystem.logger')
    def test_read_json_returns_none_for_invalid_json(self, mock_logger):
        fp = self.path('bad.json')
        with open(fp, 'w', encoding='utf-8') as f:
            f.write('{not valid json')
        result = read_json(fp)
        self.assertIsNone(result)
        mock_logger.error.assert_called_once()


# ===========================================================================
# create_hard_link
# ===========================================================================

class TestCreateHardLink(FilesystemTestBase):

    def _make_source(self, name='src.txt', content='hello'):
        src = self.path(name)
        with open(src, 'w') as f:
            f.write(content)
        return src

    def test_creates_hard_link(self):
        src = self._make_source()
        dest = self.path('linked.txt')
        create_hard_link(src, dest)
        self.assertTrue(os.path.exists(dest))
        self.assertEqual(os.stat(src).st_ino, os.stat(dest).st_ino)

    def test_raises_when_src_missing(self):
        with self.assertRaises(Exception) as ctx:
            create_hard_link('', self.path('dest.txt'))
        self.assertIn('required', str(ctx.exception))

    def test_raises_when_dest_missing(self):
        with self.assertRaises(Exception) as ctx:
            create_hard_link(self.path('src.txt'), '')
        self.assertIn('required', str(ctx.exception))

    def test_silently_returns_when_dest_already_exists(self):
        src = self._make_source()
        dest = self.path('already.txt')
        with open(dest, 'w') as f:
            f.write('existing')
        # FileExistsError is swallowed -> no raise.
        create_hard_link(src, dest)
        self.assertTrue(os.path.exists(dest))

    @patch('utils.filesystem.logger')
    def test_logs_and_raises_on_cross_device_error(self, mock_logger):
        src = self._make_source()
        dest = self.path('dest.txt')
        err = OSError()
        err.errno = 18  # EXDEV cross-device link
        with patch.object(Path, 'hardlink_to', side_effect=err):
            with self.assertRaises(OSError):
                create_hard_link(src, dest)
        mock_logger.error.assert_called_once()

    def test_reraises_other_os_errors(self):
        src = self._make_source()
        dest = self.path('dest.txt')
        err = OSError()
        err.errno = 13  # permission denied, not cross-device
        with patch.object(Path, 'hardlink_to', side_effect=err):
            with self.assertRaises(OSError):
                create_hard_link(src, dest)


# ===========================================================================
# copy_file
# ===========================================================================

class TestCopyFile(FilesystemTestBase):

    def test_copies_file_contents(self):
        src = self.path('src.txt')
        with open(src, 'w') as f:
            f.write('payload')
        dest = self.path('dest.txt')
        copy_file(src, dest)
        with open(dest) as f:
            self.assertEqual(f.read(), 'payload')

    def test_raises_when_src_missing(self):
        with self.assertRaises(Exception) as ctx:
            copy_file('', self.path('dest.txt'))
        self.assertIn('required', str(ctx.exception))

    def test_raises_when_dest_missing(self):
        with self.assertRaises(Exception) as ctx:
            copy_file(self.path('src.txt'), '')
        self.assertIn('required', str(ctx.exception))


# ===========================================================================
# get_all_dirs_in_dir
# ===========================================================================

class TestGetAllDirsInDir(FilesystemTestBase):

    def test_returns_only_directories(self):
        os.mkdir(self.path('dir1'))
        os.mkdir(self.path('dir2'))
        with open(self.path('file.txt'), 'w') as f:
            f.write('x')
        result = get_all_dirs_in_dir(self.tmp)
        self.assertEqual(len(result), 2)
        self.assertTrue(all(os.path.isdir(d) for d in result))

    def test_returns_empty_list_when_no_subdirs(self):
        with open(self.path('only_file.txt'), 'w') as f:
            f.write('x')
        self.assertEqual(get_all_dirs_in_dir(self.tmp), [])


# ===========================================================================
# recursively_rm_dir
# ===========================================================================

class TestRecursivelyRmDir(FilesystemTestBase):

    def test_removes_directory_tree(self):
        target = self.path('tree')
        os.makedirs(os.path.join(target, 'nested'))
        with open(os.path.join(target, 'nested', 'f.txt'), 'w') as f:
            f.write('x')
        recursively_rm_dir(target)
        self.assertFalse(os.path.exists(target))

    def test_noop_when_path_does_not_exist(self):
        # Must not raise.
        recursively_rm_dir(self.path('nope'))

    def test_noop_when_path_is_a_file(self):
        fp = self.path('a_file.txt')
        with open(fp, 'w') as f:
            f.write('x')
        recursively_rm_dir(fp)
        # File is left untouched since it isn't a directory.
        self.assertTrue(os.path.exists(fp))


# ===========================================================================
# does_path_exist
# ===========================================================================

class TestDoesPathExist(FilesystemTestBase):

    def test_true_for_existing_file(self):
        fp = self.path('exists.txt')
        with open(fp, 'w') as f:
            f.write('x')
        self.assertTrue(does_path_exist(fp))

    def test_true_for_existing_dir(self):
        self.assertTrue(does_path_exist(self.tmp))

    def test_false_for_missing_path(self):
        self.assertFalse(does_path_exist(self.path('nope')))


if __name__ == '__main__':
    unittest.main()

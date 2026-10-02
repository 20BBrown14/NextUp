import unittest
from unittest.mock import patch, MagicMock

from utils.load_env import load_env


class TestLoadEnv(unittest.TestCase):

    @patch('utils.logger.get_logger')
    @patch('dotenv.load_dotenv')
    def test_calls_load_dotenv(self, mock_load_dotenv, mock_get_logger):
        mock_get_logger.return_value = MagicMock()
        load_env()
        mock_load_dotenv.assert_called_once()

    @patch('utils.logger.get_logger')
    @patch('dotenv.load_dotenv')
    def test_loads_config_env_path(self, mock_load_dotenv, mock_get_logger):
        mock_get_logger.return_value = MagicMock()
        load_env()
        # The leading slash in join(..., '/config/config.env') makes the result
        # an absolute path regardless of sys.path[0].
        dotenv_path = mock_load_dotenv.call_args[0][0]
        self.assertEqual(dotenv_path, '/config/config.env')

    @patch('utils.logger.get_logger')
    @patch('dotenv.load_dotenv')
    def test_logs_error_when_load_dotenv_raises(self, mock_load_dotenv, mock_get_logger):
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        mock_load_dotenv.side_effect = RuntimeError('boom')
        # Exception is caught inside load_env, not propagated.
        load_env()
        mock_logger.error.assert_called_once()

    @patch('utils.logger.get_logger')
    @patch('dotenv.load_dotenv')
    def test_does_not_raise_on_failure(self, mock_load_dotenv, mock_get_logger):
        mock_get_logger.return_value = MagicMock()
        mock_load_dotenv.side_effect = Exception('bad')
        try:
            load_env()
        except Exception:
            self.fail('load_env should swallow exceptions')


if __name__ == '__main__':
    unittest.main()

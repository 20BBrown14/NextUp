import unittest
from unittest.mock import patch, MagicMock
import requests

from utils.fetch import make_request


class TestMakeRequest(unittest.TestCase):

    @patch('utils.fetch.requests.request')
    def test_returns_response_on_success(self, mock_request):
        resp = MagicMock()
        mock_request.return_value = resp
        result = make_request('http://x/api')
        self.assertIs(result, resp)

    @patch('utils.fetch.requests.request')
    def test_passes_through_all_arguments(self, mock_request):
        mock_request.return_value = MagicMock()
        make_request(
            'http://x/api',
            method='POST',
            params={'p': 1},
            body={'b': 2},
            headers={'H': 'v'},
            timeout=15,
        )
        _, kwargs = mock_request.call_args
        self.assertEqual(kwargs['method'], 'POST')
        self.assertEqual(kwargs['url'], 'http://x/api')
        self.assertEqual(kwargs['params'], {'p': 1})
        self.assertEqual(kwargs['json'], {'b': 2})
        self.assertEqual(kwargs['headers'], {'H': 'v'})
        self.assertEqual(kwargs['timeout'], 15)

    @patch('utils.fetch.requests.request')
    def test_body_is_sent_as_json_kwarg(self, mock_request):
        mock_request.return_value = MagicMock()
        make_request('http://x', body={'key': 'value'})
        self.assertEqual(mock_request.call_args[1]['json'], {'key': 'value'})

    @patch('utils.fetch.requests.request')
    def test_uppercases_method(self, mock_request):
        mock_request.return_value = MagicMock()
        make_request('http://x', method='post')
        self.assertEqual(mock_request.call_args[1]['method'], 'POST')

    @patch('utils.fetch.requests.request')
    def test_calls_raise_for_status(self, mock_request):
        resp = MagicMock()
        mock_request.return_value = resp
        make_request('http://x')
        resp.raise_for_status.assert_called_once()

    @patch('utils.fetch.requests.request')
    def test_defaults_to_get_method(self, mock_request):
        mock_request.return_value = MagicMock()
        make_request('http://x')
        self.assertEqual(mock_request.call_args[1]['method'], 'GET')

    @patch('utils.fetch.logger')
    @patch('utils.fetch.requests.request')
    def test_logs_request_by_default(self, mock_request, mock_logger):
        mock_request.return_value = MagicMock()
        make_request('http://x')
        mock_logger.info.assert_called_once()

    @patch('utils.fetch.logger')
    @patch('utils.fetch.requests.request')
    def test_suppresses_log_when_should_log_false(self, mock_request, mock_logger):
        mock_request.return_value = MagicMock()
        make_request('http://x', should_log=False)
        mock_logger.info.assert_not_called()

    @patch('utils.fetch.requests.request')
    def test_reraises_request_exception(self, mock_request):
        mock_request.side_effect = requests.exceptions.ConnectionError('down')
        with self.assertRaises(requests.exceptions.RequestException):
            make_request('http://x')

    @patch('utils.fetch.requests.request')
    def test_reraises_http_error_from_raise_for_status(self, mock_request):
        resp = MagicMock()
        resp.raise_for_status.side_effect = requests.exceptions.HTTPError('500')
        mock_request.return_value = resp
        with self.assertRaises(requests.exceptions.HTTPError):
            make_request('http://x')

    @patch('utils.fetch.logger')
    @patch('utils.fetch.requests.request')
    def test_logs_error_on_failure(self, mock_request, mock_logger):
        mock_request.side_effect = requests.exceptions.Timeout('slow')
        with self.assertRaises(requests.exceptions.RequestException):
            make_request('http://x')
        mock_logger.error.assert_called_once()


if __name__ == '__main__':
    unittest.main()

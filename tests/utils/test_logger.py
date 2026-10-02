import unittest
import logging
import tempfile
import os
import uuid

from utils.logger import get_logger


class LoggerTestBase(unittest.TestCase):
    def setUp(self):
        # Unique name per test so the global logging registry doesn't leak
        # handlers/config between cases.
        self.name = f"test_logger_{uuid.uuid4().hex}"

    def tearDown(self):
        logger = logging.getLogger(self.name)
        for handler in list(logger.handlers):
            handler.close()
            logger.removeHandler(handler)


class TestGetLogger(LoggerTestBase):

    def test_returns_logger_instance(self):
        logger = get_logger(self.name)
        self.assertIsInstance(logger, logging.Logger)

    def test_logger_has_requested_name(self):
        logger = get_logger(self.name)
        self.assertEqual(logger.name, self.name)

    def test_default_level_is_info(self):
        logger = get_logger(self.name)
        self.assertEqual(logger.level, logging.INFO)

    def test_custom_level_is_applied(self):
        logger = get_logger(self.name, level=logging.DEBUG)
        self.assertEqual(logger.level, logging.DEBUG)

    def test_adds_console_handler(self):
        logger = get_logger(self.name)
        stream_handlers = [h for h in logger.handlers if isinstance(h, logging.StreamHandler)]
        self.assertGreaterEqual(len(stream_handlers), 1)

    def test_does_not_duplicate_handlers_on_repeat_calls(self):
        logger = get_logger(self.name)
        count_after_first = len(logger.handlers)
        get_logger(self.name)
        get_logger(self.name)
        self.assertEqual(len(logger.handlers), count_after_first)

    def test_adds_file_handler_when_log_file_given(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = os.path.join(tmp, 'app.log')
            logger = get_logger(self.name, log_file=log_path)
            file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
            self.assertEqual(len(file_handlers), 1)
            # Close handlers before the temp dir is removed.
            for h in list(logger.handlers):
                h.close()
                logger.removeHandler(h)

    def test_no_file_handler_without_log_file(self):
        logger = get_logger(self.name)
        file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
        self.assertEqual(len(file_handlers), 0)

    def test_handlers_use_configured_formatter(self):
        logger = get_logger(self.name)
        handler = logger.handlers[0]
        self.assertIsNotNone(handler.formatter)
        # Format a sample record and confirm the expected field layout.
        record = logging.LogRecord(self.name, logging.INFO, __file__, 1, 'hi', None, None)
        formatted = handler.formatter.format(record)
        self.assertIn('INFO', formatted)
        self.assertIn('hi', formatted)
        self.assertIn(self.name, formatted)


if __name__ == '__main__':
    unittest.main()



def load_env():
    import sys
    from os.path import join
    from dotenv import load_dotenv
    from utils import logger

    logger = logger.get_logger(__name__)

    try:
        dotenv_path = join(sys.path[0], 'config.env')
        load_dotenv(dotenv_path)
    except Exception as e:
        logger.error(f"An error occurred loading env: {e}")
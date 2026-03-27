

def load_env():
    import sys
    from os.path import join, dirname
    from dotenv import load_dotenv
    try:
        dotenv_path = join(sys.path[0], 'config.env')
        load_dotenv(dotenv_path)
    except Exception as e:
        print(f"An error occurred loading env: {e}")
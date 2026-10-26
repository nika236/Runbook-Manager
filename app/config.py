import os
from pathlib import Path

from dotenv import load_dotenv

_env_path = Path(__file__).resolve().parent.parent / '.env'
load_dotenv(_env_path, override=True)


class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key')

    CONFLUENCE_BASE_URL = os.getenv('CONFLUENCE_BASE_URL', '')
    CONFLUENCE_SITE_BASE_URL = os.getenv(
        'CONFLUENCE_SITE_BASE_URL',
        os.getenv('CONFLUENCE_BASE_URL', '').rstrip('/') + '/wiki'
        if os.getenv('CONFLUENCE_BASE_URL') else ''
    )
    CONFLUENCE_EMAIL = os.getenv('CONFLUENCE_EMAIL', '')
    CONFLUENCE_API_TOKEN = os.getenv('CONFLUENCE_API_TOKEN', '')
    CONFLUENCE_SPACE_KEYS = [
        s.strip() for s in os.getenv('CONFLUENCE_SPACE_KEYS', '').split(',') if s.strip()
    ]
    CONFLUENCE_CLOUD_ID = os.getenv('CONFLUENCE_CLOUD_ID', '')

    STALE_THRESHOLD_DAYS = int(os.getenv('STALE_THRESHOLD_DAYS', '30'))
    REVIEW_AGE_DAYS = int(os.getenv('REVIEW_AGE_DAYS', '365'))

    _project_root = Path(__file__).resolve().parent.parent
    _raw_data_dir = os.getenv('DATA_DIR', 'data')
    DATA_DIR = str(
        Path(_raw_data_dir) if Path(_raw_data_dir).is_absolute()
        else _project_root / _raw_data_dir
    )

    CONFLUENCE_RATE_LIMIT = int(os.getenv('CONFLUENCE_RATE_LIMIT', '8'))

import logging
import os
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

from app.services.confluence_client import ConfluenceClient
from app.services.store import PageStore
from app.services.metadata_store import MetadataStore
from app.services.sync_service import SyncService

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(name)s %(levelname)s %(message)s')


def create_app():
    app = Flask(__name__)
    app.config.from_object('app.config.Config')

    CORS(app, origins=[
        'http://localhost:4747',
        'http://localhost:5173',
        'http://localhost:5174',
        'http://localhost:5175',
        'http://localhost:5176',
    ])

    confluence = ConfluenceClient(
        base_url=app.config['CONFLUENCE_BASE_URL'],
        email=app.config['CONFLUENCE_EMAIL'],
        api_token=app.config['CONFLUENCE_API_TOKEN'],
        rate_limit=app.config.get('CONFLUENCE_RATE_LIMIT', 8),
    )

    data_dir = app.config['DATA_DIR']

    page_store = PageStore(
        data_dir=data_dir,
        stale_threshold_days=app.config['STALE_THRESHOLD_DAYS'],
        review_age_days=app.config.get('REVIEW_AGE_DAYS', 365),
    )

    metadata_store = MetadataStore(data_dir=data_dir)
    metadata_store.load_cache()

    sync_service = SyncService(
        confluence_client=confluence,
        data_dir=data_dir,
        stale_threshold_days=app.config['STALE_THRESHOLD_DAYS'],
    )

    from app.services.confluence_renderer import build_user_lookup, render_storage_format
    user_lookup = build_user_lookup(data_dir)

    app.extensions['confluence_client'] = confluence
    app.extensions['page_store'] = page_store
    app.extensions['metadata_store'] = metadata_store
    app.extensions['sync_service'] = sync_service
    app.extensions['user_lookup'] = user_lookup
    # `context` is optional so existing single-argument callers keep working; the
    # page-detail endpoints pass one so internal links resolve.
    app.extensions['render_content'] = (
        lambda html, context=None: render_storage_format(html, user_lookup, context)
    )

    from app.api.runbooks import runbooks_bp
    from app.api.dashboard import dashboard_bp
    from app.api.sync import sync_bp

    app.register_blueprint(runbooks_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(sync_bp)

    @app.route('/api/health')
    def health():
        return jsonify({'status': 'ok'}), 200

    static_dir = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'dist')
    if os.path.isdir(static_dir):
        @app.route('/', defaults={'path': ''})
        @app.route('/<path:path>')
        def serve_frontend(path):
            full = os.path.join(static_dir, path)
            if path and os.path.isfile(full):
                return send_from_directory(static_dir, path)
            return send_from_directory(static_dir, 'index.html')

    return app

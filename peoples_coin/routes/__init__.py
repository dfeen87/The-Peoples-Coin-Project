# peoples_coin/routes/__init__.py
"""
This module imports all blueprint instances from the route modules
and provides a function to register them on the Flask app.
"""
import os
import logging
from flask import Flask

# --- Import all of your blueprints ---
from .api_routes import user_api_bp
from .auth_routes import auth_bp
from .goodwill_routes import goodwill_bp
from .blockchain_routes import blockchain_bp
from .circulatory_routes import circulatory_bp
from .cognitive_routes import cognitive_bp
from .endocrine_routes import endocrine_bp
from .governance_routes import governance_bp
from .immune_routes import immune_bp
from .metabolic_routes import metabolic_bp
from .nervous_routes import nervous_bp
from .reproductive_routes import reproductive_bp
from .status_routes import status_bp

logger = logging.getLogger(__name__)

def register_routes(app: Flask):
    """Register all blueprints with the Flask app."""
    
    # The url_prefix is already defined in each blueprint, so you don't need it here.
    app.register_blueprint(user_api_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(goodwill_bp)
    app.register_blueprint(blockchain_bp)
    app.register_blueprint(circulatory_bp)
    app.register_blueprint(cognitive_bp)
    app.register_blueprint(endocrine_bp)
    app.register_blueprint(governance_bp)
    app.register_blueprint(immune_bp)
    app.register_blueprint(metabolic_bp)
    app.register_blueprint(nervous_bp)
    app.register_blueprint(reproductive_bp)
    app.register_blueprint(status_bp)

    # Conditionally register traditional banking plugin blueprint and middleware
    enable_banking = os.getenv("ENABLE_BANKING_PLUGIN", "").lower() in ("true", "1", "yes")
    if enable_banking:
        from peoples_coin.banking_plugin import banking_plugin_blueprint, banking_security_middleware
        app.register_blueprint(banking_plugin_blueprint)
        banking_security_middleware(app)
        logger.info("🔒 Traditional Banking Security Plugin registered and active.")

    logger.info("✅ All application blueprints registered.")

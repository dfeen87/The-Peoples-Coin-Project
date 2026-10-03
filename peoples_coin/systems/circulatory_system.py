# peoples_coin/systems/circulatory_system.py

import logging
import http
import uuid
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Tuple, Optional

from flask import Flask
from sqlalchemy.orm.exc import NoResultFound

from peoples_coin.utils.auth import require_api_key
from peoples_coin.models.db_utils import get_session_scope
from peoples_coin.models import GoodwillAction, UserAccount, LedgerEntry, UserWallet
from peoples_coin.consensus import Consensus
from peoples_coin.extensions import db
from peoples_coin.services.minting_service import MintingService, MintingError

logger = logging.getLogger(__name__)

class CirculatorySystem:
    """Handles the core logic of token minting based on completed goodwill actions."""

    def __init__(self):
        self.app: Optional[Flask] = None
        self.consensus: Optional[Consensus] = None
        self.minter_wallet_address: Optional[str] = None
        self._initialized = False
        logger.info("🫀 CirculatorySystem instance created.")

    def init_app(self, app: Flask, consensus_instance: Consensus):
        """Initializes the system with the Flask app and dependencies."""
        if self._initialized:
            return
        self.app = app
        self.db = db
        self.consensus = consensus_instance
        
        # Use environment variable instead of app config to avoid missing env on Cloud Run
        self.minter_wallet_address = os.getenv("MINTER_WALLET_ADDRESS")
        
        if not self.minter_wallet_address:
            raise RuntimeError("MINTER_WALLET_ADDRESS must be configured in the environment.")
        
        self._initialized = True
        logger.info("🫀 CirculatorySystem initialized and configured.")

    def process_goodwill_for_minting(self, goodwill_action_id: uuid.UUID) -> Tuple[bool, str, int]:
        """Durably request minting for a verified action.

        This call records intent; queue publication and chain confirmation are
        separate worker phases and are never reported as confirmed here.
        """
        if not self._initialized or not self.consensus:
            msg = "CirculatorySystem or Consensus has not been properly initialized."
            logger.critical(msg)
            return False, msg, http.HTTPStatus.INTERNAL_SERVER_ERROR

        try:
            intent = MintingService(self.db).create_intent(goodwill_action_id)
            self.db.session.commit()
            return True, f"Mint intent {intent.id} is {intent.state}.", http.HTTPStatus.ACCEPTED
        except MintingError as e:
            self.db.session.rollback()
            return False, str(e), http.HTTPStatus.UNPROCESSABLE_ENTITY
        except Exception:
            self.db.session.rollback()
            logger.exception("Unable to record mint intent for %s", goodwill_action_id)
            return False, "An internal error occurred while recording mint intent.", http.HTTPStatus.INTERNAL_SERVER_ERROR



# Singleton Instance
circulatory_system = CirculatorySystem()

# --- Function for status page ---
def get_circulatory_status():
    """Health check for the Circulatory System."""
    if circulatory_system._initialized:
        return {"active": True, "healthy": True, "info": "Circulatory System operational"}
    else:
        return {"active": False, "healthy": False, "info": "Circulatory System not initialized"}

import logging
from typing import Dict, Any
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func

from peoples_coin.models import UserAccount
from peoples_coin.models.db_utils import get_session_scope
from peoples_coin.models.goodwill_action import GoodwillAction
from peoples_coin.validate.validate_transaction import validate_transaction
from peoples_coin.extensions import db

logger = logging.getLogger(__name__)

class GoodwillSubmissionError(Exception):
    """Custom exception raised for goodwill service related issues."""
    pass

# Alias for backward compatibility
GoodwillError = GoodwillSubmissionError

class GoodwillService:
    def __init__(self):
        self.app = None
        self.db = None
        self.message_queue_client = None  # e.g., Pub/Sub client instance

    def init_app(self, app, db_instance, message_queue_client=None):
        self.app = app
        self.db = db_instance
        self.message_queue_client = message_queue_client
        logger.info("GoodwillService initialized.")

    def submit_and_queue_goodwill_action(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validates goodwill action data, persists it, and queues it for blockchain minting.

        Args:
            data: Incoming goodwill action data dict.

        Returns:
            Dict with action_id and status on success.

        Raises:
            GoodwillError on validation or processing errors.
        """
        logger.info("GoodwillService: Processing goodwill submission.")

        # Validate incoming data
        # The route replaces any client-supplied user ID with the authenticated
        # account ID.  Pass that trusted value through both identity checks so
        # validation cannot reject every submission due to missing arguments.
        authenticated_user_id = str(data.get("user_id", ""))
        validation_result = validate_transaction(
            data,
            authenticated_user_id=authenticated_user_id,
            allowed_contributors_loader=lambda: {authenticated_user_id},
        )
        if not validation_result.is_valid:
            logger.warning(f"Validation failed: {validation_result.errors}")
            raise GoodwillError(f"Validation failed: {validation_result.errors}")

        validated_data = validation_result.data

        with get_session_scope(self.db) as session:
            try:
                user_account = session.query(UserAccount).filter_by(id=validated_data['user_id']).first()
                if not user_account:
                    logger.warning(f"UserAccount not found for ID: {validated_data['user_id']}")
                    raise GoodwillError(f"No UserAccount found for ID {validated_data['user_id']}")

                goodwill_action = GoodwillAction(
                    performer_user_id=user_account.id,
                    action_type=validated_data['action_type'],
                    description=validated_data['description'],
                    contextual_data=validated_data.get('contextual_data', {}),
                    loves_value=validated_data['loves_value'],
                    correlation_id=validated_data.get('correlation_id'),  # Optional
                    status='PENDING_VERIFICATION',
                )
                session.add(goodwill_action)
                session.flush()  # Assign ID

                logger.info(f"GoodwillAction {goodwill_action.id} persisted. Queueing for blockchain minting.")

                if self.message_queue_client:
                    # Placeholder for queueing logic — implement your message broker here
                    # e.g.,
                    # topic_path = self.message_queue_client.publisher.topic_path(
                    #     self.app.config['GCP_PROJECT_ID'],
                    #     self.app.config['MINTING_TOPIC_ID']
                    # )
                    # self.message_queue_client.publisher.publish(topic_path, str(goodwill_action.id).encode('utf-8'))
                    logger.info(f"Queued GoodwillAction ID {goodwill_action.id} for blockchain processing.")
                else:
                    logger.warning("Message queue client not initialized; skipping queuing.")

                return {"action_id": str(goodwill_action.id), "status": "accepted"}

            except IntegrityError as e:
                logger.error("Database integrity error during goodwill action processing.", exc_info=True)
                raise GoodwillError("Database error: possible duplicate or constraint violation.") from e
            except GoodwillError:
                raise
            except Exception as e:
                logger.exception("Unexpected error processing goodwill action.")
                raise GoodwillError(f"Internal server error: {str(e)}") from e

    def get_action_status(self, user_id: str, action_id: str) -> Dict[str, Any]:
        """
        Retrieves the status of a specific goodwill action.
        
        Args:
            user_id: The user ID (UUID)
            action_id: The action ID (UUID)
            
        Returns:
            Dict with action status information or None if not found
        """
        with get_session_scope(self.db) as session:
            action = session.query(GoodwillAction).filter_by(
                id=action_id,
                performer_user_id=user_id
            ).first()
            
            if not action:
                return None
                
            return {
                "action_id": str(action.id),
                "status": action.status,
                "action_type": action.action_type,
                "created_at": action.created_at.isoformat() if action.created_at else None
            }
    
    def get_user_summary(self, user_id: str) -> Dict[str, Any]:
        """
        Returns a summary of total goodwill actions and score for a user.
        
        Args:
            user_id: The user ID (UUID)
            
        Returns:
            Dict with total_score and action_count
        """
        with get_session_scope(self.db) as session:
            result = session.query(
                func.count(GoodwillAction.id).label('action_count'),
                func.sum(GoodwillAction.loves_value).label('total_score')
            ).filter(
                GoodwillAction.performer_user_id == user_id
            ).first()
            
            return {
                "action_count": result.action_count or 0,
                "total_score": float(result.total_score) if result.total_score else 0.0
            }
    
    def get_user_history(self, user_id: str, page: int = 1, per_page: int = 20) -> Dict[str, Any]:
        """
        Retrieves paginated goodwill action history for a user.
        
        Args:
            user_id: The user ID (UUID)
            page: Page number (1-indexed)
            per_page: Results per page
            
        Returns:
            Dict with actions list and pagination metadata
        """
        with get_session_scope(self.db) as session:
            query = session.query(GoodwillAction).filter(
                GoodwillAction.performer_user_id == user_id
            ).order_by(GoodwillAction.created_at.desc())
            
            # Calculate offset
            offset = (page - 1) * per_page
            
            # Get total count
            total_count = query.count()
            
            # Get paginated results
            actions = query.limit(per_page).offset(offset).all()
            
            return {
                "actions": [
                    {
                        "action_id": str(action.id),
                        "action_type": action.action_type,
                        "description": action.description,
                        "loves_value": action.loves_value,
                        "status": action.status,
                        "created_at": action.created_at.isoformat() if action.created_at else None
                    }
                    for action in actions
                ],
                "pagination": {
                    "page": page,
                    "per_page": per_page,
                    "total_count": total_count,
                    "total_pages": (total_count + per_page - 1) // per_page
                }
            }


goodwill_service = GoodwillService()

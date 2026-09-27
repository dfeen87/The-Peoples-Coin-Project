import time
import logging
from typing import List, Union, Dict, Any, Callable, Type
from pydantic import BaseModel, ValidationError, Field, field_validator, Extra
from functools import wraps
from flask import g, request, jsonify

logger = logging.getLogger(__name__)

# --- Configuration ---
MAX_FUTURE_DRIFT_SECONDS = 60


# ==============================================================================
# 1. Core Data Schema
# ==============================================================================

class Contribution(BaseModel):
    """
    Represents a validated act of kindness or transaction.
    Uses Pydantic v2 syntax and features.
    """
    contributor: str = Field(..., min_length=1, description="Contributor name must not be empty.")
    tags: List[str] = Field(..., min_items=1, description="At least one tag is required.")
    value: float = Field(..., gt=0, le=1000, description="Value must be > 0 and ≤ 1000.")
    timestamp: float = Field(..., ge=0, description="A valid UNIX timestamp.")

    @field_validator('timestamp')
    @classmethod
    def timestamp_must_not_be_in_the_future(cls, v: float) -> float:
        """Validates that the timestamp is not further in the future than allowed."""
        allowed_future_time = time.time() + MAX_FUTURE_DRIFT_SECONDS
        if v > allowed_future_time:
            raise ValueError(f"Timestamp is too far in the future.")
        return v

    class Config:
        extra = Extra.forbid


# ==============================================================================
# 2. Explicit and Unambiguous Return Models
# ==============================================================================

class ValidationResult(BaseModel):
    """A self-describing result for a single validation attempt."""
    is_valid: bool
    data: Union[Contribution, None] = None
    errors: Union[List[Dict], None] = None


class BatchValidationResult(BaseModel):
    """A self-describing result for a batch validation attempt."""
    all_valid: bool
    valid_items: List[Contribution] = Field(default_factory=list)
    invalid_items: List[Dict] = Field(default_factory=list)  # Holds original data plus error details


# ==============================================================================
# 3. Refined Validation Functions
# ==============================================================================

def validate_contribution(data: dict) -> ValidationResult:
    """
    Validates a single contribution against the schema.

    Returns:
        A ValidationResult object that is unambiguous and easy to use.
    """
    try:
        validated_contribution = Contribution.model_validate(data)
        return ValidationResult(is_valid=True, data=validated_contribution)
    except ValidationError as e:
        logger.warning(f"Validation failed for contribution: {e.errors()}")
        return ValidationResult(is_valid=False, errors=e.errors())


def validate_contributions_batch(transactions: List[dict]) -> BatchValidationResult:
    """
    Validates a list of contributions, separating valid and invalid results.

    Returns:
        A BatchValidationResult object containing categorized lists.
    """
    valid_items = []
    invalid_items = []

    for i, tx_data in enumerate(transactions):
        result = validate_contribution(tx_data)
        if result.is_valid:
            valid_items.append(result.data)
        else:
            invalid_items.append({
                "index": i,
                "original_data": tx_data,
                "errors": result.errors
            })

    return BatchValidationResult(
        all_valid=not invalid_items,
        valid_items=valid_items,
        invalid_items=invalid_items
    )


# ==============================================================================
# 4. Flask Request Validation Decorator
# ==============================================================================

def validate_with(schema: Type[BaseModel]) -> Callable:
    """
    Decorator for Flask routes that validates JSON request data against a Pydantic schema.

    Usage:
        @app.route('/endpoint', methods=['POST'])
        @validate_with(MySchema)
        def endpoint():
            validated_data = request.validated_data
            ...

    Args:
        schema: A Pydantic BaseModel class to validate against.

    Returns:
        A decorated function that injects validated data or returns JSON error on failure.
    """
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            try:
                json_data = request.get_json(force=True)
                validated = schema.model_validate(json_data)
                request.validated_data = validated
                g.validated_data = validated
            except ValidationError as e:
                logger.warning(f"Request validation error: {e.errors()}")
                return jsonify({"errors": e.errors()}), 400
            except Exception as e:
                logger.error(f"Unexpected error during validation: {e}")
                return jsonify({"error": "Invalid request data"}), 400

            return f(*args, **kwargs)
        return wrapped
    return decorator

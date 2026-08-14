# peoples_coin/constants.py

from enum import Enum

__version__ = "4.0.0"

class GoodwillStatus(Enum):
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"

class ApiResponseStatus(Enum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"


"""
PCI-DSS Data Controls for Traditional Banking Security Plugin.
Provides PAN masking, structured sanitization, sensitive field zero-logging,
and encrypted memory buffers.
"""

import re
import copy
import base64
import os
from typing import Any, Dict, Union
from cryptography.fernet import Fernet

# Regex patterns for PAN (Primary Account Numbers) and SSN
PAN_PATTERN = re.compile(r'\b(?:\d[ -]*?){13,19}\b')
SSN_PATTERN = re.compile(r'\b\d{3}-\d{2}-\d{4}\b')

SENSITIVE_KEYS = {
    'card_number', 'pan', 'cvv', 'cvc', 'ssn', 'social_security_number',
    'pin', 'password', 'secret', 'account_secret', 'private_key'
}


class PCIDataManager:
    """Handles PCI-DSS compliant sanitization, masking, and encrypted buffering."""

    def __init__(self, encryption_key: bytes = None):
        if not encryption_key:
            # Generate or load a Fernet key
            encryption_key = Fernet.generate_key()
        self.fernet = Fernet(encryption_key)

    @staticmethod
    def mask_pan(pan: str) -> str:
        """Masks PAN / Card Number leaving only last 4 digits visible."""
        digits = re.sub(r'\D', '', str(pan))
        if len(digits) < 13 or len(digits) > 19:
            return "*****"
        return f"{'*' * (len(digits) - 4)}{digits[-4:]}"

    @staticmethod
    def mask_ssn(ssn: str) -> str:
        """Masks SSN leaving only last 4 digits visible."""
        digits = re.sub(r'\D', '', str(ssn))
        if len(digits) == 9:
            return f"***-**-{digits[-4:]}"
        return "***-**-****"

    def sanitize_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively masks sensitive values in a dictionary."""
        if not isinstance(data, dict):
            return data

        cleaned = copy.deepcopy(data)
        for key, value in cleaned.items():
            key_lower = str(key).lower()
            if key_lower in SENSITIVE_KEYS:
                if key_lower in {'card_number', 'pan'}:
                    cleaned[key] = self.mask_pan(str(value))
                elif key_lower in {'ssn', 'social_security_number'}:
                    cleaned[key] = self.mask_ssn(str(value))
                else:
                    cleaned[key] = "[REDACTED]"
            elif isinstance(value, dict):
                cleaned[key] = self.sanitize_dict(value)
            elif isinstance(value, list):
                cleaned[key] = [
                    self.sanitize_dict(item) if isinstance(item, dict) else item
                    for item in value
                ]
            elif isinstance(value, str):
                # Pattern match inline PAN or SSN inside general text string
                if PAN_PATTERN.search(value):
                    cleaned[key] = PAN_PATTERN.sub(lambda m: self.mask_pan(m.group(0)), value)
                if SSN_PATTERN.search(value):
                    cleaned[key] = SSN_PATTERN.sub(lambda m: self.mask_ssn(m.group(0)), value)

        return cleaned

    def zero_log_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Completely strips sensitive fields before logging."""
        if not isinstance(data, dict):
            return data

        cleaned = copy.deepcopy(data)
        for key in list(cleaned.keys()):
            key_lower = str(key).lower()
            if key_lower in SENSITIVE_KEYS:
                del cleaned[key]
            elif isinstance(cleaned[key], dict):
                cleaned[key] = self.zero_log_dict(cleaned[key])
            elif isinstance(cleaned[key], list):
                cleaned[key] = [
                    self.zero_log_dict(item) if isinstance(item, dict) else item
                    for item in cleaned[key]
                ]
        return cleaned

    def encrypt_buffer(self, sensitive_bytes: bytes) -> bytes:
        """Encrypts sensitive data in memory using Fernet symmetric encryption."""
        return self.fernet.encrypt(sensitive_bytes)

    def decrypt_buffer(self, encrypted_bytes: bytes) -> bytes:
        """Decrypts encrypted in-memory data buffer."""
        return self.fernet.decrypt(encrypted_bytes)


pci_manager = PCIDataManager()

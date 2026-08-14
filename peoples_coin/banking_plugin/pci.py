"""
PCI-DSS Data Controls for Traditional Banking Security Plugin.
Provides PAN masking, structured sanitization, sensitive field zero-logging,
encrypted memory buffers, and PCI compliance validation.
"""

import re
import copy
from typing import Any, Dict, Tuple
from cryptography.fernet import Fernet

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

    def validate_pci_compliance(self, data: Any) -> Tuple[bool, str]:
        """
        Fail-closed check to detect unmasked raw PAN or SSN in input data.
        Returns (True, '') if compliant, or (False, 'violation reason') if unmasked PAN/SSN is detected.
        """
        if isinstance(data, dict):
            for k, v in data.items():
                if str(k).lower() in {'card_number', 'pan', 'cvv', 'cvc'}:
                    if isinstance(v, str) and not v.startswith('*') and len(re.sub(r'\D', '', v)) >= 13:
                        return False, f"Unmasked card number/PAN in field '{k}'"
                    if str(k).lower() in {'cvv', 'cvc'} and v:
                        return False, f"Forbidden storage of CVV/CVC in field '{k}'"
                valid, reason = self.validate_pci_compliance(v)
                if not valid:
                    return False, reason
        elif isinstance(data, list):
            for item in data:
                valid, reason = self.validate_pci_compliance(item)
                if not valid:
                    return False, reason
        elif isinstance(data, str):
            if PAN_PATTERN.search(data) and not '*' in data:
                return False, "Unmasked Primary Account Number (PAN) detected in string payload"
        return True, ""

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

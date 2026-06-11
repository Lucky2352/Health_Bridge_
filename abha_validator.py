"""
ABHA ID Validator for Ayushman Bharat Health Account
"""
import re

class ABHAValidator:
    @staticmethod
    def validate_abha_id(abha_id):
        """
        Validate ABHA ID format
        Returns: (is_valid: bool, error_message: str)
        """
        if not abha_id:
            return True, ""  # Empty is allowed
        
        # Remove any formatting characters
        cleaned = ABHAValidator.clean_abha_id(abha_id)
        
        # Check if it's exactly 14 digits
        if not cleaned.isdigit():
            return False, "ABHA ID must contain only numbers"
        
        if len(cleaned) != 14:
            return False, "ABHA ID must be exactly 14 digits"
        
        return True, ""
    
    @staticmethod
    def clean_abha_id(abha_id):
        """
        Remove all non-digit characters from ABHA ID
        """
        if not abha_id:
            return ""
        return re.sub(r'[^0-9]', '', abha_id)
    
    @staticmethod
    def format_abha_id(abha_id):
        """
        Format ABHA ID with hyphens: XX-XXXX-XXXX-XXXX
        """
        cleaned = ABHAValidator.clean_abha_id(abha_id)
        if len(cleaned) == 14:
            return f"{cleaned[:2]}-{cleaned[2:6]}-{cleaned[6:10]}-{cleaned[10:14]}"
        return abha_id
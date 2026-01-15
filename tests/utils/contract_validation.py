"""
Contract validation utilities for testing.

Provides helpers for validating data against JSON schema contracts.
Implements T006: Contract test utilities.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional

import jsonschema
from jsonschema import Draft7Validator, ValidationError


class ContractValidator:
    """Validator for JSON schema contracts."""
    
    def __init__(self, contract_dir: Path):
        """
        Initialize validator with contract directory.
        
        Args:
            contract_dir: Directory containing JSON schema files
        """
        self.contract_dir = contract_dir
        self._schemas: Dict[str, dict] = {}
    
    def load_schema(self, schema_name: str) -> dict:
        """
        Load JSON schema from contract directory.
        
        Args:
            schema_name: Name of schema file (e.g., "a2a-mcp-handoff.json")
            
        Returns:
            Loaded JSON schema
        """
        if schema_name in self._schemas:
            return self._schemas[schema_name]
        
        schema_path = self.contract_dir / schema_name
        if not schema_path.exists():
            raise FileNotFoundError(f"Schema not found: {schema_path}")
        
        with open(schema_path, "r") as f:
            schema = json.load(f)
        
        self._schemas[schema_name] = schema
        return schema
    
    def validate(
        self, 
        data: Any, 
        schema_name: str,
        raise_on_error: bool = True
    ) -> tuple[bool, Optional[str]]:
        """
        Validate data against schema.
        
        Args:
            data: Data to validate
            schema_name: Name of schema file
            raise_on_error: Whether to raise exception on validation failure
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        schema = self.load_schema(schema_name)
        validator = Draft7Validator(schema)
        
        try:
            validator.validate(data)
            return (True, None)
        except ValidationError as e:
            error_msg = f"Validation failed: {e.message}"
            if raise_on_error:
                raise ValidationError(error_msg) from e
            return (False, error_msg)
    
    def validate_all_required_fields(
        self,
        data: dict,
        schema_name: str
    ) -> tuple[bool, list[str]]:
        """
        Check if all required fields are present.
        
        Args:
            data: Data dictionary to check
            schema_name: Name of schema file
            
        Returns:
            Tuple of (all_present, missing_fields)
        """
        schema = self.load_schema(schema_name)
        required_fields = schema.get("required", [])
        
        missing = [field for field in required_fields if field not in data]
        return (len(missing) == 0, missing)


def get_contract_validator(feature_name: str) -> ContractValidator:
    """
    Get contract validator for a feature.
    
    Args:
        feature_name: Feature directory name (e.g., "005-kickstart-assessment")
        
    Returns:
        ContractValidator instance
    """
    project_root = Path(__file__).parent.parent.parent
    contract_dir = project_root / "specs" / feature_name / "contracts"
    
    if not contract_dir.exists():
        raise FileNotFoundError(f"Contract directory not found: {contract_dir}")
    
    return ContractValidator(contract_dir)


__all__ = ["ContractValidator", "get_contract_validator"]

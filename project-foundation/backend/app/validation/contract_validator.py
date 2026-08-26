"""
Contract Validator

Validates data against JSON schemas defined in contracts.
"""

import json
from pathlib import Path
from typing import Any

import jsonschema
from jsonschema import Draft7Validator, validators

from app.config import get_settings
from app.core.interfaces import IValidator
from app.exceptions import ContractNotFoundError, SchemaValidationError
from app.logging import LoggerMixin
from app.models import ValidationResult


class ContractValidator(IValidator[dict[str, Any]], LoggerMixin):
    """
    Validates data against JSON schema contracts.

    Supports all standard JSON Schema Draft 7 features.
    """

    def __init__(self) -> None:
        """Initialize contract validator."""
        super().__init__()
        settings = get_settings()
        self.contracts_dir = Path(settings.contract.contracts_dir)
        self._schema_cache: dict[str, dict[str, Any]] = {}
        self._validation_errors: list[str] = []

    def _load_schema(self, contract_name: str) -> dict[str, Any]:
        """
        Load JSON schema from contract file.

        Args:
            contract_name: Name of the contract

        Returns:
            JSON schema dictionary

        Raises:
            ContractNotFoundError: If contract file doesn't exist
        """
        # Check cache first
        if contract_name in self._schema_cache:
            return self._schema_cache[contract_name]

        # Load from file
        contract_path = self.contracts_dir / f"{contract_name}.json"

        if not contract_path.exists():
            raise ContractNotFoundError(
                f"Contract not found: {contract_name}",
                contract_name=contract_name,
            )

        try:
            with open(contract_path, "r", encoding="utf-8") as f:
                schema = json.load(f)

            # Cache the schema
            self._schema_cache[contract_name] = schema

            self.logger.info("contract_loaded", contract_name=contract_name)

            return schema

        except Exception as e:
            self.logger.error(
                "contract_load_failed",
                contract_name=contract_name,
                error=str(e),
            )
            raise ContractNotFoundError(
                f"Failed to load contract {contract_name}: {str(e)}",
                contract_name=contract_name,
            )

    async def validate(self, data: dict[str, Any]) -> bool:
        """
        Validate data against its contract schema.

        Args:
            data: Data to validate (must have '$schema' or 'contract' field)

        Returns:
            True if valid

        Raises:
            SchemaValidationError: If validation fails
        """
        self._validation_errors = []

        # Determine contract name from data
        contract_name = data.get("$schema") or data.get("contract")

        if not contract_name:
            raise SchemaValidationError(
                "Data must specify contract name in '$schema' or 'contract' field"
            )

        try:
            # Load schema
            schema = self._load_schema(contract_name)

            # Validate
            validator = Draft7Validator(schema)
            errors = list(validator.iter_errors(data))

            if errors:
                # Format error messages
                self._validation_errors = [
                    f"{'.'.join(str(p) for p in error.path)}: {error.message}"
                    for error in errors
                ]

                self.logger.warning(
                    "validation_failed",
                    contract_name=contract_name,
                    errors=self._validation_errors,
                )

                raise SchemaValidationError(
                    f"Validation failed for contract {contract_name}",
                    errors=self._validation_errors,
                )

            self.logger.info("validation_success", contract_name=contract_name)
            return True

        except SchemaValidationError:
            raise
        except Exception as e:
            self.logger.error(
                "validation_error",
                contract_name=contract_name,
                error=str(e),
            )
            raise SchemaValidationError(f"Validation error: {str(e)}")

    async def validate_with_contract(
        self, data: dict[str, Any], contract_name: str
    ) -> ValidationResult:
        """
        Validate data against specific contract and return detailed result.

        Args:
            data: Data to validate
            contract_name: Name of the contract

        Returns:
            Validation result with details
        """
        self._validation_errors = []

        try:
            # Load schema
            schema = self._load_schema(contract_name)

            # Validate
            validator = Draft7Validator(schema)
            errors = list(validator.iter_errors(data))

            if errors:
                error_messages = [
                    f"{'.'.join(str(p) for p in error.path)}: {error.message}"
                    for error in errors
                ]

                return ValidationResult(
                    is_valid=False,
                    errors=error_messages,
                    warnings=[],
                    metadata={"contract_name": contract_name},
                )

            return ValidationResult(
                is_valid=True,
                errors=[],
                warnings=[],
                metadata={"contract_name": contract_name},
            )

        except Exception as e:
            self.logger.error(
                "validation_error",
                contract_name=contract_name,
                error=str(e),
            )
            return ValidationResult(
                is_valid=False,
                errors=[str(e)],
                warnings=[],
                metadata={"contract_name": contract_name},
            )

    def get_validation_errors(self) -> list[str]:
        """Get list of validation errors from last validation."""
        return self._validation_errors.copy()

    def clear_cache(self) -> None:
        """Clear schema cache."""
        self._schema_cache.clear()
        self.logger.info("schema_cache_cleared")

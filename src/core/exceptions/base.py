from typing import Dict, Optional


class AppError(Exception):
    """Base exception class for application-specific errors"""

    def __init__(self, message: str, error_code: str, details: Optional[Dict] = None):
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)


class ValidationError(AppError):
    """Validation error"""

    def __init__(self, message: str, field: str, details: Optional[Dict] = None):
        super().__init__(message=message, error_code="VALIDATION_ERROR", details={"field": field, **(details or {})})


class ResourceNotFoundError(AppError):
    """Resource not found error"""

    def __init__(self, resource_type: str, resource_id: str, details: Optional[Dict] = None):
        super().__init__(
            message=f"{resource_type} not found: {resource_id}",
            error_code="RESOURCE_NOT_FOUND",
            details={"resource_type": resource_type, "resource_id": resource_id, **(details or {})},
        )


class ConfigurationError(AppError):
    """Configuration-related errors"""

    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(message, "CONFIGURATION_ERROR", details)


class ExternalServiceError(AppError):
    """External service communication errors"""

    def __init__(self, service: str, message: str, details: Optional[Dict] = None):
        super().__init__(
            message=f"{service} service error: {message}",
            error_code="EXTERNAL_SERVICE_ERROR",
            details={"service": service, **(details or {})},
        )

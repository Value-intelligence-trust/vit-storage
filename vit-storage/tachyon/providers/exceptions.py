class StorageError(Exception):
    """Base exception for all storage providers."""
    def __init__(self, message: str, code: str = "storage_error", status_code: int = 500):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code

class ProviderUnavailable(StorageError):
    """Exception raised when a provider is offline or timed out."""
    def __init__(self, message: str, code: str = "provider_unavailable"):
        super().__init__(message, code=code, status_code=503)

class FileNotFoundError(StorageError):
    """Exception raised when a requested file or directory does not exist."""
    def __init__(self, message: str, code: str = "file_not_found"):
        super().__init__(message, code=code, status_code=404)

class AuthenticationError(StorageError):
    """Exception raised when credentials fail."""
    def __init__(self, message: str, code: str = "authentication_error"):
        super().__init__(message, code=code, status_code=401)

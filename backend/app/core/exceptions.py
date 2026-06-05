class AppError(Exception):
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class NotFoundError(AppError):
    def __init__(self, resource: str, resource_id: str):
        super().__init__(f"{resource} not found: {resource_id}", status_code=404)


class ConnectionError(AppError):
    def __init__(self, message: str):
        super().__init__(f"Database connection error: {message}", status_code=502)


class ValidationError(AppError):
    def __init__(self, message: str):
        super().__init__(message, status_code=422)


class AuthenticationError(AppError):
    def __init__(self, message: str = "Not authenticated"):
        super().__init__(message, status_code=401)


class AuthorizationError(AppError):
    def __init__(self, message: str = "Not authorized"):
        super().__init__(message, status_code=403)


class SQLSafetyError(AppError):
    def __init__(self, message: str):
        super().__init__(f"SQL safety violation: {message}", status_code=403)


class QueryTimeoutError(AppError):
    def __init__(self, timeout_seconds: int):
        super().__init__(
            f"Query exceeded timeout of {timeout_seconds} seconds", status_code=408
        )

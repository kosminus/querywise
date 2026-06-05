from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.exceptions import AppError
from app.core.telemetry import REQUEST_ID_HEADER, get_request_id


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.message, "request_id": get_request_id()},
            headers={REQUEST_ID_HEADER: get_request_id()},
        )

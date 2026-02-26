from fastapi import APIRouter

from app.api.v1.endpoints import (
    connections,
    dictionary,
    glossary,
    health,
    knowledge,
    metrics,
    query,
    query_history,
    sample_queries,
    schemas,
)

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(query.router)
api_router.include_router(connections.router)
api_router.include_router(schemas.router)
api_router.include_router(glossary.router)
api_router.include_router(metrics.router)
api_router.include_router(dictionary.router)
api_router.include_router(sample_queries.router)
api_router.include_router(query_history.router)
api_router.include_router(knowledge.router)

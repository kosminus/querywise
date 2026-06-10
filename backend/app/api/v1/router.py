from fastapi import APIRouter

from app.api.v1.endpoints import (
    analytics,
    api_keys,
    assistant,
    audit,
    auth,
    catalog,
    compilation,
    connections,
    dashboards,
    dictionary,
    glossary,
    health,
    knowledge,
    metrics,
    policies,
    query,
    query_history,
    sample_queries,
    saved_queries,
    schedules,
    schemas,
    teams,
)

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(teams.router)
api_router.include_router(api_keys.router)
api_router.include_router(query.router)
api_router.include_router(assistant.router)
api_router.include_router(connections.router)
api_router.include_router(schemas.router)
api_router.include_router(glossary.router)
api_router.include_router(metrics.router)
api_router.include_router(dictionary.router)
api_router.include_router(sample_queries.router)
api_router.include_router(saved_queries.router)
api_router.include_router(dashboards.router)
api_router.include_router(query_history.router)
api_router.include_router(knowledge.router)
api_router.include_router(catalog.router)
api_router.include_router(compilation.router)
api_router.include_router(audit.router)
api_router.include_router(schedules.router)
api_router.include_router(policies.router)
api_router.include_router(analytics.router)

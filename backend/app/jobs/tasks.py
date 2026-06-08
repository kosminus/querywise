"""Importing this module registers every background job.

The arq worker imports it so the registry is populated in the worker process.
In the web process, jobs are registered as a side effect of importing the
services that define them (e.g. ``setup_service`` at startup); importing this
module makes that registration explicit and order-independent.
"""

# Registers "generate_embeddings".
import app.services.setup_service  # noqa: F401

# Registers "run_schedule".
import app.jobs.scheduler  # noqa: F401

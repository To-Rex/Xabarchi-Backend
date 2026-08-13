"""Business logic services.

Services orchestrate repositories and Redis events. They are framework-free
(no FastAPI imports): inputs are schemas/primitives, failures are AppErrors,
and the HTTP layer in ``app.api`` stays a thin adapter.
"""

"""The HTTP API, laid out the way FastAPI's "Bigger Applications" guide recommends:

    app.py            create_app(): lifespan, middleware, error handlers, routers
    dependencies.py   the database pool and connection, the LLM client, shared parameter types
    errors.py         the one error response shape, and its handlers
    companies.py · rankings.py · questions.py · operations.py    one router each

Run with: uvicorn tracker.api:app --port 8000   (Docker does this for you)
"""

from tracker.api.app import create_app

app = create_app()

"""/ask: plain-English questions, answered by the agent."""

from fastapi import APIRouter, Depends

from tracker import agent
from tracker.api.dependencies import Model, Pool, ask_slot
from tracker.api.errors import error_responses
from tracker.config import get_settings
from tracker.models import Answer, Question

router = APIRouter(tags=["questions"], responses=error_responses(422, 429, 503, 504))


@router.post("/ask", dependencies=[Depends(ask_slot)])
def ask(body: Question, pool: Pool, model: Model) -> Answer:
    """The answer says which data it used (`route`) and where it came from (`sources`)."""
    # Takes the pool, not a connection: the agent borrows one per tool call rather than holding
    # one for the whole conversation with the model.
    return agent.ask(model, pool, body.question, get_settings().ask_timeout_seconds)

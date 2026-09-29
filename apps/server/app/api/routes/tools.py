"""Route exposing the catalog of built-in tools an agent can be given."""

from fastapi import APIRouter

from app.llm.tools import AVAILABLE_TOOLS
from app.schemas.agent import ToolProfile

router = APIRouter(prefix="/agents", tags=["tools"])


@router.get("/tools", response_model=list[ToolProfile])
async def list_tools():
    return AVAILABLE_TOOLS

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.agents.rentwise_agent import RentWiseAgent
from app.core.config import Settings, get_settings
from app.schemas.agent import (
    AgentChatRequest,
    AgentChatResponse,
    CommunityDiscoveryRequest,
    CommunityDiscoveryResponse,
    CommunityIntakeRequest,
    CommunityIntakeResponse,
    CommunityReportRequest,
    CommunityReportResponse,
    CommunitySearchRequest,
    CommunitySearchResponse,
)
from app.workflows.community_discovery import run_community_discovery_workflow
from app.workflows.community_intake import run_community_intake_workflow

router = APIRouter()


@router.post("/community-intake", response_model=CommunityIntakeResponse)
def community_intake(
    req: CommunityIntakeRequest,
    db: Session = Depends(get_db),
) -> CommunityIntakeResponse:
    return run_community_intake_workflow(
        db=db,
        community_name=req.community_name,
    )


@router.post("/community-discovery", response_model=CommunityDiscoveryResponse)
async def community_discovery(
    req: CommunityDiscoveryRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> CommunityDiscoveryResponse:
    return await run_community_discovery_workflow(
        db=db,
        community_name=req.community_name,
        city=req.city,
        state=req.state,
        settings=settings,
    )


@router.post("/community-search", response_model=CommunitySearchResponse)
async def community_search(
    req: CommunitySearchRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> CommunitySearchResponse:
    agent = RentWiseAgent(db=db, settings=settings)
    return await agent.search_community(
        community_name=req.community_name,
        city=req.city,
        state=req.state,
    )


@router.post("/community-report", response_model=CommunityReportResponse)
async def community_report(
    req: CommunityReportRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> CommunityReportResponse:
    agent = RentWiseAgent(db=db, settings=settings)
    return await agent.generate_community_report(
        community_id=req.community_id,
        user_preferences=req.user_preferences,
    )


@router.post("/chat", response_model=AgentChatResponse)
async def agent_chat(
    req: AgentChatRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AgentChatResponse:
    agent = RentWiseAgent(db=db, settings=settings)
    return await agent.chat(req.messages)

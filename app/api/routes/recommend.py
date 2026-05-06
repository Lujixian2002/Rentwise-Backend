from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.recommendation import RecommendationRequest, RecommendationResponse
from app.services.recommend_service import recommend_communities

router = APIRouter()


@router.post("", response_model=RecommendationResponse)
def recommend(
    req: RecommendationRequest,
    db: Session = Depends(get_db),
) -> RecommendationResponse:
    return recommend_communities(
        db=db,
        weights=req.weights,
        top_k=req.top_k,
    )

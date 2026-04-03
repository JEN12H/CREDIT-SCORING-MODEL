"""
Scoring Routes
Credit scoring prediction endpoints.
"""
import logging
from typing import Any, Dict
from fastapi import APIRouter, HTTPException
from src.api.schemas import ColdStartInput, FullModelInput, ScoringResponse, PredictionRequest
from src.core.monitoring import prediction_tracker
from src.db.turso import get_customer_profile, get_customer_history
from src.data.feature_pipeline import calculate_single_user_features

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/predict", tags=["Scoring"])

def _build_response(result: Dict[str, Any], model_type: str) -> ScoringResponse:
    return ScoringResponse(
        model_type=model_type,
        customer_tier=result.get("customer_tier", 0),
        tier_description=result.get("tier_description", ""),
        account_age_months=result.get("account_age_months", 0),
        default_probability=round(result.get("ml_probability", 0.0), 4),
        credit_score=result.get("final_score", 0),
        decision=result.get("decision", "Unknown"),
        max_credit_limit=result.get("max_credit_limit", 0),
        model_used=result.get("model_used", "unknown"),
        recommendation=result.get("recommendation"),
        risk_warnings=result.get("risk_warnings", []),
        note=result.get("note"),
    )

# Handler reference — set by app.py at startup
_handler = None

def set_handler(handler):
    global _handler
    _handler = handler

def _require_handler():
    if _handler is None:
        raise HTTPException(
            status_code=503,
            detail="Scoring handler not initialized. Ensure models are trained and restart the server.",
        )

@router.post("/auto", response_model=ScoringResponse)
def predict_auto(request: PredictionRequest):
    _require_handler()
    try:
        # 1. Fetch data from DB
        profile = get_customer_profile(request.customer_id)
        if not profile:
            raise HTTPException(status_code=404, detail=f"Customer {request.customer_id} not found.")
            
        # We use the existing monthly history to calculate features for now, 
        # as raw_transactions just got created and is empty.
        history = get_customer_history(request.customer_id)
        
        # 2. Calculate ML features dynamically
        #    If history is too short, fall back to cold-start model automatically
        try:
            features = calculate_single_user_features(profile, history)
            # 3a. Full model scoring (enough history available)
            result = _handler.score_customer(features)
        except ValueError:
            # 3b. Cold-start fallback (new customer, < 4 months history)
            logger.info(f"Customer {request.customer_id}: insufficient history ({len(history)} months), using cold-start model.")
            cold_start_data = {
                "age":                profile.get("age", 25),
                "employment_status":  profile.get("employment_status", "Salaried"),
                "education_level":    profile.get("education_level", "Graduate"),
                "monthly_income":     profile.get("monthly_income", 0),
                "credit_limit":       profile.get("credit_limit", 0),
                "city_tier":          profile.get("city_tier", "Tier-2"),
                "dependents":         profile.get("dependents", 0),
                "residence_type":     profile.get("residence_type", "Rented"),
                "account_age_months": profile.get("account_age_months", 0),
            }
            result = _handler.score_cold_start(cold_start_data)
            tier, tier_desc = _handler.get_customer_tier(cold_start_data["account_age_months"])
            result.update({
                "customer_tier":      tier,
                "tier_description":   tier_desc,
                "account_age_months": cold_start_data["account_age_months"],
                "note":               f"Scored using cold-start model ({len(history)} months of history available).",
            })
        
        # 4. Final Response Generation
        response = _build_response(result, model_type="auto_routed")
        prediction_tracker.record(
            probability=response.default_probability,
            score=response.credit_score,
            decision=response.decision,
        )
        return response
    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.exception("Unexpected error in /predict/auto")
        raise HTTPException(status_code=500, detail=f"Internal scoring error: {e}")

@router.post("/cold-start", response_model=ScoringResponse)
def predict_cold_start(data: ColdStartInput):
    _require_handler()
    try:
        customer = data.model_dump()
        result = _handler.score_cold_start(customer)
        tier, tier_desc = _handler.get_customer_tier(data.account_age_months)
        result.update({
            "customer_tier":      tier,
            "tier_description":   tier_desc,
            "account_age_months": data.account_age_months,
        })
        response = _build_response(result, model_type="cold_start_forced")
        prediction_tracker.record(
            probability=response.default_probability,
            score=response.credit_score,
            decision=response.decision,
        )
        return response
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.exception("Unexpected error in /predict/cold-start")
        raise HTTPException(status_code=500, detail=f"Internal scoring error: {e}")

@router.post("/full", response_model=ScoringResponse)
def predict_full_model(data: FullModelInput):
    _require_handler()
    try:
        customer = data.model_dump()
        result = _handler.score_established(customer)
        tier, tier_desc = _handler.get_customer_tier(data.account_age_months)
        result.update({
            "customer_tier":      tier,
            "tier_description":   tier_desc,
            "account_age_months": data.account_age_months,
        })
        response = _build_response(result, model_type="full_model_forced")
        prediction_tracker.record(
            probability=response.default_probability,
            score=response.credit_score,
            decision=response.decision,
        )
        return response
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.exception("Unexpected error in /predict/full")
        raise HTTPException(status_code=500, detail=f"Internal scoring error: {e}")

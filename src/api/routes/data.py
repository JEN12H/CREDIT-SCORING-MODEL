"""
Data Routes
Customer and behavior CRUD endpoints backed by Supabase.
"""
import logging
from fastapi import APIRouter, HTTPException
from src.api.schemas import BehaviorCreate, CustomerCreate
from src.db.supabase import (add_behavior_record, add_customer, get_customer, get_customer_history, get_raw_transaction_history)
from src.data.generate_customers import assign_credit_limit

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Database"])

@router.post("/customers/", status_code=201)
def create_customer(customer: CustomerCreate):
    try:
        data = customer.model_dump()

        # Auto-compute credit_limit if not provided by caller
        if not data.get("credit_limit"):
            data["credit_limit"] = assign_credit_limit(
                employment_status = data["employment_status"],
                monthly_income    = data["monthly_income"],
                education_level   = data["education_level"],
                age               = data["age"],
            )
            logger.info(
                f"Auto-assigned credit_limit=₹{data['credit_limit']:,} "
                f"for customer {data['customer_id']} "
                f"({data['employment_status']}, income=₹{data['monthly_income']:,})"
            )

        result = add_customer(data)
        return {
            "status": "created",
            "credit_limit_assigned": data["credit_limit"],  # show frontend what was set
            "data": result,
        }
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.exception("Error adding customer")
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

@router.post("/customers/{customer_id}/behavior", status_code=201)
def add_monthly_behavior(customer_id: int, behavior: BehaviorCreate):
    try:
        data = behavior.model_dump()
        data["customer_id"] = customer_id
        result = add_behavior_record(data)
        return {"status": "created", "data": result}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.exception("Error adding behavior record")
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

@router.get("/customers/{customer_id}/history")
def get_history(customer_id: int):
    try:
        profile = get_customer(customer_id)
        history = get_customer_history(customer_id)
        return {
            "customer_id":    customer_id,
            "profile":        profile,
            "behavior_months": len(history),
            "history":        history,
        }
    except Exception as e:
        logger.exception("Error fetching customer history")
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

@router.get("/customers/{customer_id}/transactions")
def get_raw_transactions(customer_id: int):
    """Fetch the raw, itemized ledger of a customer's transactions."""
    try:
        raw_txns = get_raw_transaction_history(customer_id)
        return {
            "customer_id": customer_id,
            "total_transactions": len(raw_txns),
            "transactions": raw_txns,
        }
    except Exception as e:
        logger.exception("Error fetching raw transactions")
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

"""
Data Routes
Customer and behavior CRUD endpoints backed by Supabase.
"""
import logging
from typing import Literal
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from src.api.schemas import BehaviorCreate, CustomerCreate
from src.db.supabase import (add_behavior_record, add_customer, get_customer, get_customer_history, get_raw_transaction_history, supabase)
from src.data.generate_customers import assign_credit_limit

class RawTransactionCreate(BaseModel):
    """A single individual transaction — the atomic unit of customer activity."""
    amount:           float   = Field(..., gt=0, description="Transaction amount in INR (must be > 0)")
    transaction_type: Literal["Purchase", "Repayment", "Penalty"] = Field(
        ..., description="Type: 'Purchase' (spending), 'Repayment' (paying bill), 'Penalty' (late fee)"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "amount": 350.0,
                "transaction_type": "Purchase"
            }
        }
    }

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

@router.post("/customers/{customer_id}/transactions", status_code=201)
def add_raw_transaction(customer_id: int, txn: RawTransactionCreate):
    """
    Log a single individual transaction for a customer.
    Examples: ₹150 grocery purchase, ₹500 electricity bill, ₹1000 repayment.

    transaction_type must be one of:
      - 'Purchase'  — customer spent money (groceries, bills, shopping, etc.)
      - 'Repayment' — customer paid their credit bill
      - 'Penalty'   — a late fee was charged

    These raw transactions are automatically aggregated into monthly
    behavior records every 1st of the month during the retraining cycle.
    """
    try:
        # Verify customer exists first
        customer = get_customer(customer_id)
        if not customer:
            raise HTTPException(status_code=404, detail=f"Customer {customer_id} not found.")

        payload = {
            "customer_id":       customer_id,
            "amount":            txn.amount,
            "transaction_type":  txn.transaction_type,
        }
        result = supabase.table("raw_transactions").insert(payload).execute()
        logger.info(f"Transaction logged: customer={customer_id}, type={txn.transaction_type}, amount=₹{txn.amount}")
        return {
            "status":  "created",
            "message": f"₹{txn.amount:.2f} {txn.transaction_type} logged for customer {customer_id}",
            "data":    result.data[0] if result.data else {},
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error adding raw transaction")
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

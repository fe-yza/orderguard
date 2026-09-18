from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from orderguard.api.schemas import OrderDetailOut
from orderguard.persistence import repository
from orderguard.persistence.database import get_session

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("/{order_id}", response_model=OrderDetailOut)
def get_order(order_id: str, session: Session = Depends(get_session)) -> OrderDetailOut:
    """The Order Inspector's data source: timeline, risk factor history, and
    every intervention decision (with its full cost-comparison candidates)
    ever made for this order."""
    order = repository.get_order_detail(session, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return OrderDetailOut.model_validate(order)

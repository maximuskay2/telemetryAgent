"""Proof shop API: the app TelemetryAgent watches end to end."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import FastAPI
from pydantic import BaseModel, Field

from app.cart import summary

app = FastAPI(title="proof-shop")


class CartItem(BaseModel):
    name: str = Field(min_length=1)
    price: float = Field(ge=0)
    qty: int = Field(ge=0)


class CheckoutIn(BaseModel):
    items: List[CartItem] = Field(default_factory=list)


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/checkout")
def checkout(payload: CheckoutIn) -> Dict[str, Any]:
    # No try/except on purpose: the empty-cart ZeroDivisionError must crash
    # with a full traceback so the forwarder ships it to TelemetryAgent.
    return summary([item.model_dump() for item in payload.items])

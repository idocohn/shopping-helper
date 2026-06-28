from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone

class Product(BaseModel):
    source: str = "hahishook"
    product_id: Optional[str] = None
    name: str
    brand: Optional[str] = None
    category: Optional[str] = None
    size_text: Optional[str] = None
    price_nis: Optional[float] = None
    unit_price_text: Optional[str] = None
    bulk_price_text: Optional[str] = None
    saving_text: Optional[str] = None
    badges: List[str] = Field(default_factory=list)
    product_url: Optional[str] = None
    image_url: Optional[str] = None
    in_stock: Optional[bool] = None
    raw_text: Optional[str] = None
    scraped_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

from datetime import datetime

from pydantic.dataclasses import dataclass


@dataclass
class Product:
    id: int
    name: str
    description: str
    created_at: datetime

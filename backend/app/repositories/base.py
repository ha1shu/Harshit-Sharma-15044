from __future__ import annotations

from typing import Any, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

ModelType = TypeVar("ModelType")


class BaseRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, model: type[ModelType], item_id: int) -> ModelType | None:
        return self.session.get(model, item_id)

    def list(self, model: type[ModelType], **filters: Any):
        stmt = select(model)
        for field_name, value in filters.items():
            if value is not None:
                stmt = stmt.where(getattr(model, field_name) == value)
        return self.session.execute(stmt).scalars().all()

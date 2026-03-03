from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime


class TheatreCreate(BaseModel):
    name: str
    columns: int = Field(..., ge=5, le=30)
    rows: int = Field(..., ge=3, le=20)

    def model_dump(self, **kwargs) -> dict:
        data = super().model_dump(**kwargs)
        total_seats = data.get('columns', 15) * data.get('rows', 8)
        return {
            'name': data.get('name'),
            'total_seats': total_seats,
            'layout_json': {
                'columns': data.get('columns'),
                'rows': data.get('rows'),
            }
        }


class TheatreUpdate(BaseModel):
    name: Optional[str] = None
    columns: Optional[int] = Field(None, ge=5, le=30)
    rows: Optional[int] = Field(None, ge=3, le=20)

    def model_dump(self, exclude_unset: bool = False, **kwargs) -> dict:
        data = super().model_dump(exclude_unset=exclude_unset, **kwargs)

        # Only include fields that are set
        result = {}
        if data.get('name') is not None:
            result['name'] = data['name']

        # Recalculate total_seats if columns or rows changed
        if data.get('columns') is not None or data.get('rows') is not None:
            result['layout_json'] = {
                'columns': data.get('columns'),
                'rows': data.get('rows'),
            }

        return result


class Theatre(BaseModel):
    id: int
    name: str
    total_seats: int
    layout_json: Optional[Any] = None
    is_active: Optional[bool] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SeatCreate(BaseModel):
    theatre_id: int
    row_label: str = Field(..., min_length=1, max_length=2)
    seat_number: int = Field(..., ge=1, le=100)
    is_active: bool = True


class SeatUpdate(BaseModel):
    is_active: Optional[bool] = None


class Seat(BaseModel):
    id: int
    theatre_id: int
    row_label: str
    seat_number: int
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

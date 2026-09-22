from pydantic import BaseModel, ConfigDict


class CategoryCreate(BaseModel):
    name: str
    is_active: bool = True
    parent_id: int | None = None
    description: str | None = None

class CategoryUpdate(BaseModel):
    name: str | None = None
    is_active: bool | None = None
    parent_id: int | None = None    
    description: str | None = None


class CategoryResponse(BaseModel):
    id: int
    tenant_id: int
    parent_id: int | None
    name: str
    is_active: bool = True
    description: str | None = None

    model_config = ConfigDict(from_attributes=True)
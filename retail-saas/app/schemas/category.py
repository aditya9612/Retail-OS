from pydantic import BaseModel, ConfigDict


class CategoryCreate(BaseModel):
    name: str
    description: str | None = None
    parent_id: int | None = None


class CategoryResponse(BaseModel):
    id: int
    tenant_id: int
    parent_id: int | None
    name: str
    description: str | None

    model_config = ConfigDict(from_attributes=True)
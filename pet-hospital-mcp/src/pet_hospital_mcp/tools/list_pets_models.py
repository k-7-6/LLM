"""Input / output models for the list_pets MCP tool."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


# --- Backend-allowed enum values (sourced from /api/v1/meta) ---

_SPECIES_OPTIONS = ("犬", "猫", "兔", "鸟", "仓鼠", "爬宠", "其他")
_STATUS_OPTIONS = ("待就诊", "就诊中", "住院中", "已康复", "慢性病随访")
_SORT_FIELDS = (
    "id",
    "name",
    "ownerName",
    "species",
    "doctor",
    "disease",
    "status",
    "totalCost",
    "visitCount",
    "createdAt",
    "updatedAt",
)
_ORDER_OPTIONS = ("asc", "desc")


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------


class ListPetsInput(BaseModel):
    """Input parameters for the list_pets tool, mirroring GET /api/v1/pets."""

    q: str | None = Field(default=None, description="Full-text search query")
    name: str | None = Field(default=None, description="Pet name filter")
    owner_name: str | None = Field(
        default=None,
        description="Owner name filter (snake_case alias)",
        alias="ownerName",
    )
    owner_phone: str | None = Field(
        default=None,
        description="Owner phone filter (snake_case alias)",
        alias="ownerPhone",
    )
    species: str | None = Field(
        default=None,
        description="Species filter",
    )
    doctor: str | None = Field(
        default=None,
        description="Doctor name filter",
    )
    disease: str | None = Field(
        default=None,
        description="Disease / diagnosis filter",
    )
    status: str | None = Field(
        default=None,
        description="Visit status filter",
    )
    min: float | None = Field(
        default=None,
        description="Minimum total cost filter",
        ge=0,
    )
    max: float | None = Field(
        default=None,
        description="Maximum total cost filter",
        ge=0,
    )
    sort_by: str | None = Field(
        default=None,
        description="Sort field",
        alias="sortBy",
    )
    order: str | None = Field(
        default=None,
        description="Sort order: asc or desc",
    )
    page: int = Field(default=1, ge=1, description="Page number (1-based)")
    page_size: int = Field(
        default=20,
        ge=1,
        le=500,
        description="Items per page (1-500)",
        alias="pageSize",
    )

    model_config = {"populate_by_name": True, "extra": "forbid"}

    @field_validator("species")
    @classmethod
    def validate_species(cls, v: str | None) -> str | None:
        if v is not None and v not in _SPECIES_OPTIONS:
            raise ValueError(
                f"species must be one of: {', '.join(_SPECIES_OPTIONS)}"
            )
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v is not None and v not in _STATUS_OPTIONS:
            raise ValueError(
                f"status must be one of: {', '.join(_STATUS_OPTIONS)}"
            )
        return v

    @field_validator("sort_by")
    @classmethod
    def validate_sort_by(cls, v: str | None) -> str | None:
        if v is not None and v not in _SORT_FIELDS:
            raise ValueError(
                f"sortBy must be one of: {', '.join(_SORT_FIELDS)}"
            )
        return v

    @field_validator("order")
    @classmethod
    def validate_order(cls, v: str | None) -> str | None:
        if v is not None and v not in _ORDER_OPTIONS:
            raise ValueError(f"order must be one of: {', '.join(_ORDER_OPTIONS)}")
        return v

    @model_validator(mode="after")
    def validate_min_max(self) -> "ListPetsInput":
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("min must be <= max")
        return self

    def to_query_params(self) -> dict[str, str]:
        """Convert to backend query parameters (camelCase keys)."""
        params: dict[str, str] = {}
        if self.q is not None:
            params["q"] = self.q
        if self.name is not None:
            params["name"] = self.name
        if self.owner_name is not None:
            params["ownerName"] = self.owner_name
        if self.owner_phone is not None:
            params["ownerPhone"] = self.owner_phone
        if self.species is not None:
            params["species"] = self.species
        if self.doctor is not None:
            params["doctor"] = self.doctor
        if self.disease is not None:
            params["disease"] = self.disease
        if self.status is not None:
            params["status"] = self.status
        if self.min is not None:
            params["min"] = str(self.min)
        if self.max is not None:
            params["max"] = str(self.max)
        if self.sort_by is not None:
            params["sortBy"] = self.sort_by
        if self.order is not None:
            params["order"] = self.order
        params["page"] = str(self.page)
        params["pageSize"] = str(self.page_size)
        return params


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


class PetRecord(BaseModel):
    """A single visit record in the pet's medical history."""

    id: str
    visit_date: str = Field(alias="visitDate")
    doctor: str
    diagnosis: str
    symptoms: str
    treatment: str
    prescription: list[str]
    weight_kg: float = Field(alias="weightKg")
    temperature: float
    follow_up: str = Field(alias="followUp")
    charge: float
    created_at: str = Field(alias="createdAt")


class PetCharge(BaseModel):
    """A single charge item in the pet's billing history."""

    id: str
    item: str
    category: str
    amount: float
    doctor: str
    date: str


class PetItem(BaseModel):
    """A pet record as returned by GET /api/v1/pets."""

    id: str
    name: str
    species: str
    breed: str
    gender: str
    age_months: int = Field(alias="ageMonths")
    color: str
    owner_name: str = Field(alias="ownerName")
    owner_phone: str = Field(alias="ownerPhone")
    owner_addr: str = Field(alias="ownerAddr")
    doctor: str
    disease: str
    status: str
    allergy: str
    note: str
    records: list[PetRecord] | None = None
    charges: list[PetCharge] | None = None
    total_cost: float = Field(alias="totalCost")
    visit_count: int = Field(alias="visitCount")
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")


class ListPetsSuccess(BaseModel):
    """The data envelope returned by the list_pets tool."""

    items: list[PetItem]
    total: int
    page: int
    page_size: int = Field(alias="pageSize")
    total_pages: int = Field(alias="totalPages")
    total_cost: float = Field(alias="totalCost")

    model_config = {"populate_by_name": True}

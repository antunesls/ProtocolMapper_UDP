from fastapi import APIRouter, HTTPException, status

from app.api.schemas.mapping import MappingCreate, MappingRead, MappingUpdate
from app.db import repository as repo

router = APIRouter(prefix="/api/mappings", tags=["mappings"])


@router.get("/", response_model=list[MappingRead])
async def list_mappings():
    return await repo.list_mappings()


@router.get("/{mapping_id}", response_model=MappingRead)
async def get_mapping(mapping_id: str):
    mapping = await repo.get_mapping(mapping_id)
    if mapping is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mapping not found")
    return mapping


@router.post("/", response_model=MappingRead, status_code=status.HTTP_201_CREATED)
async def create_mapping(body: MappingCreate):
    return await repo.create_mapping(body.model_dump())


@router.put("/{mapping_id}", response_model=MappingRead)
async def update_mapping(mapping_id: str, body: MappingUpdate):
    updated = await repo.update_mapping(
        mapping_id, body.model_dump(exclude_none=True)
    )
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mapping not found")
    return updated


@router.delete("/{mapping_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mapping(mapping_id: str):
    deleted = await repo.delete_mapping(mapping_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mapping not found")

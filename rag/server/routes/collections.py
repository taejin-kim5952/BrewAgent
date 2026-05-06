from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..dependencies import AppContainer, get_container

router = APIRouter()


class CollectionInfo(BaseModel):
    namespace: str
    total_chunks: int
    total_vectors: int


class CollectionListResponse(BaseModel):
    collections: list[CollectionInfo]


@router.get("/v1/collections", response_model=CollectionListResponse)
async def list_collections(container: AppContainer = Depends(get_container)):
    namespaces = container.ns_manager.list_namespaces()
    result = []
    for ns in namespaces:
        store = container.get_faiss_store(ns)
        stats = store.get_stats()
        chunk_count = await container.metadata_store.count_chunks(ns)
        result.append(CollectionInfo(
            namespace=ns,
            total_chunks=chunk_count,
            total_vectors=stats.total_vectors,
        ))
    return CollectionListResponse(collections=result)


@router.post("/v1/collections/{namespace}", status_code=201)
async def create_collection(
    namespace: str,
    container: AppContainer = Depends(get_container),
):
    """네임스페이스 생성 (FAISS 인덱스 초기화)."""
    container.ns_manager.namespace_dir(namespace)
    container.get_faiss_store(namespace)
    return {"namespace": namespace, "status": "created"}


@router.delete("/v1/collections/{namespace}")
async def delete_collection(
    namespace: str,
    container: AppContainer = Depends(get_container),
):
    """네임스페이스 전체 삭제."""
    container.ns_manager.delete(namespace)
    container._faiss_stores.pop(namespace, None)

    docs = await container.metadata_store.list_documents(namespace)
    for doc in docs:
        await container.metadata_store.delete_document(doc.doc_id)

    return {"namespace": namespace, "status": "deleted"}

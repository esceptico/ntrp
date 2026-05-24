from fastapi import APIRouter, Depends

from ntrp.knowledge import (
    ActivationRequest,
    KnowledgeActivationService,
    KnowledgeArtifactRenderRequest,
    KnowledgeFeedbackRequest,
    KnowledgeObjectCreate,
    KnowledgeObjectStatus,
    KnowledgeObjectType,
    KnowledgeObjectUpdate,
    KnowledgeProfileSynthesisRequest,
    KnowledgePruneRequest,
    KnowledgePublishRequest,
    KnowledgeReflectRequest,
)
from ntrp.knowledge.processors import KnowledgeProcessorService
from ntrp.memory.service import MemoryService
from ntrp.server.deps import require_memory

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("/summary")
async def get_knowledge_summary(svc: MemoryService = Depends(require_memory)):
    return (await KnowledgeActivationService(svc).summary()).model_dump()


@router.get("/objects")
async def list_knowledge_objects(
    object_type: KnowledgeObjectType | None = None,
    status: KnowledgeObjectStatus | None = None,
    query: str | None = None,
    limit: int = 100,
    offset: int = 0,
    svc: MemoryService = Depends(require_memory),
):
    search = query.strip() if query else ""
    if search:
        objects = await svc.knowledge_objects.search_text(
            search,
            object_types={object_type} if object_type else None,
            statuses={status} if status else None,
            limit=limit,
            offset=offset,
        )
    else:
        objects = await svc.knowledge_objects.list(
            object_type=object_type,
            status=status,
            limit=limit,
            offset=offset,
        )
    return {"objects": [obj.model_dump() for obj in objects]}


@router.post("/objects")
async def create_knowledge_object(
    request: KnowledgeObjectCreate,
    svc: MemoryService = Depends(require_memory),
):
    return {"object": (await svc.knowledge_objects.create(request)).model_dump()}


@router.patch("/objects/{object_id}")
async def update_knowledge_object(
    object_id: int,
    request: KnowledgeObjectUpdate,
    svc: MemoryService = Depends(require_memory),
):
    return {"object": (await svc.knowledge_objects.update(object_id, request)).model_dump()}


@router.get("/objects/{object_id}/sources")
async def get_knowledge_object_sources(
    object_id: int,
    svc: MemoryService = Depends(require_memory),
):
    return (await svc.knowledge_objects.source_trace(object_id)).model_dump()


@router.post("/processors/reflect")
async def reflect_knowledge(
    request: KnowledgeReflectRequest,
    svc: MemoryService = Depends(require_memory),
):
    return (await KnowledgeProcessorService(svc).reflect(request)).model_dump()


@router.post("/processors/prune")
async def prune_knowledge(
    request: KnowledgePruneRequest,
    svc: MemoryService = Depends(require_memory),
):
    return (await KnowledgeProcessorService(svc).prune_retention(request)).model_dump()


@router.post("/processors/profiles")
async def synthesize_knowledge_profiles(
    request: KnowledgeProfileSynthesisRequest,
    svc: MemoryService = Depends(require_memory),
):
    return (await KnowledgeProcessorService(svc).synthesize_profiles(request)).model_dump()


@router.get("/processors/health")
async def knowledge_health(svc: MemoryService = Depends(require_memory)):
    return (await KnowledgeProcessorService(svc).health()).model_dump()


@router.post("/maintenance/backfill-embeddings")
async def backfill_knowledge_embeddings(
    limit: int = 1_000,
    batch_size: int = 100,
    apply: bool = False,
    svc: MemoryService = Depends(require_memory),
):
    return await svc.knowledge_objects.backfill_embeddings(limit=limit, batch_size=batch_size, apply=apply)


@router.post("/artifacts/render")
async def render_knowledge_artifact(
    request: KnowledgeArtifactRenderRequest,
    svc: MemoryService = Depends(require_memory),
):
    return {"object": (await KnowledgeProcessorService(svc).render_artifact(request)).model_dump()}


@router.post("/artifacts/publish")
async def publish_knowledge_artifact(
    request: KnowledgePublishRequest,
    svc: MemoryService = Depends(require_memory),
):
    return {"receipt": (await KnowledgeProcessorService(svc).publish(request)).model_dump()}


@router.post("/feedback")
async def record_knowledge_feedback(
    request: KnowledgeFeedbackRequest,
    svc: MemoryService = Depends(require_memory),
):
    return {"object": (await KnowledgeProcessorService(svc).feedback(request)).model_dump()}


@router.post("/activation/inspect")
async def inspect_knowledge_activation(
    request: ActivationRequest,
    svc: MemoryService = Depends(require_memory),
):
    return (await KnowledgeActivationService(svc).inspect(request)).model_dump()

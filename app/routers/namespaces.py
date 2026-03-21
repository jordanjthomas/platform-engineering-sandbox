from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.auth import require_auth
from app.models.namespace import (
    CreateNamespaceRequest,
    NamespaceDetail,
    NamespaceSummary,
)
from app.services.namespace_service import NamespaceService

router = APIRouter(prefix="/namespaces", tags=["namespaces"])


def get_namespace_service(request: Request) -> NamespaceService:
    return request.app.state.namespace_service


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_auth)],
)
def create_namespace(
    req: CreateNamespaceRequest,
    response: Response,
    service: NamespaceService = Depends(get_namespace_service),
):
    result = service.create_namespace(req)
    if not result["created"]:
        response.status_code = status.HTTP_200_OK
    return result


@router.get(
    "",
    response_model=list[NamespaceSummary],
    dependencies=[Depends(require_auth)],
)
def list_namespaces(
    team: str | None = Query(None),
    environment: str | None = Query(None),
    service: NamespaceService = Depends(get_namespace_service),
):
    return service.list_namespaces(team=team, environment=environment)


@router.get(
    "/{name}",
    response_model=NamespaceDetail,
    dependencies=[Depends(require_auth)],
)
def get_namespace(
    name: str,
    service: NamespaceService = Depends(get_namespace_service),
):
    return service.get_namespace(name)


@router.delete(
    "/{name}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_auth)],
)
def delete_namespace(
    name: str,
    force: bool = Query(False),
    service: NamespaceService = Depends(get_namespace_service),
):
    service.delete_namespace(name, force=force)

from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from apps.organizations.permissions import (
    HasActiveOrganization,
    IsOrganizationAdminOrReadOnly,
)

from ..models import Project
from .pagination import ProjectPagination
from .serializers import ProjectSerializer

csrf_header = OpenApiParameter(
    name="X-CSRFToken",
    type=OpenApiTypes.STR,
    location=OpenApiParameter.HEADER,
    required=True,
    description="Token CSRF atual; envie também os cookies csrftoken e sessionid.",
)
forbidden_response = OpenApiResponse(
    response=OpenApiTypes.OBJECT,
    description=(
        "Sessão/contexto ausente ou inválido, falha CSRF ou escrita sem role OWNER/ADMIN."
    ),
)
not_found_response = OpenApiResponse(
    response=OpenApiTypes.OBJECT,
    description="Obra não encontrada na organização ativa, inclusive IDs de outro tenant.",
)
invalid_response = OpenApiResponse(
    response=OpenApiTypes.OBJECT,
    description=(
        "Campos inválidos, datas invertidas ou cliente indisponível. Cliente de outro "
        "tenant e ID inexistente recebem o mesmo erro em customer_id."
    ),
)


@method_decorator(never_cache, name="dispatch")
@extend_schema(tags=["projects"])
@extend_schema_view(
    list=extend_schema(
        description=(
            "Lista apenas obras da organização ativa. Páginas fixas de 25 itens, "
            "ordenados por name e id, sem filtros. Leitura para qualquer Membership ativa."
        ),
        responses={200: ProjectSerializer(many=True), 403: forbidden_response},
    ),
    create=extend_schema(
        description=(
            "Cria obra na organização validada da request. Apenas name é obrigatório. "
            "customer_id é opcional e restrito ao mesmo tenant. Datas podem ser nulas; "
            "quando ambas existem, fim >= início. Organization/tenant do payload são "
            "ignorados. Exige sessão, contexto ativo, role OWNER ou ADMIN e CSRF."
        ),
        request=ProjectSerializer,
        parameters=[csrf_header],
        responses={
            201: ProjectSerializer,
            400: invalid_response,
            403: forbidden_response,
        },
    ),
    retrieve=extend_schema(
        description="Consulta obra apenas no queryset da organização ativa.",
        responses={
            200: ProjectSerializer,
            403: forbidden_response,
            404: not_found_response,
        },
    ),
    partial_update=extend_schema(
        description=(
            "Atualiza obra do tenant ativo, sem transferi-la. customer_id aceita cliente "
            "do mesmo tenant ou null. Datas são validadas junto aos valores persistidos "
            "quando o PATCH omite um dos campos. Exige role OWNER ou ADMIN e CSRF."
        ),
        request=ProjectSerializer,
        parameters=[csrf_header],
        responses={
            200: ProjectSerializer,
            400: invalid_response,
            403: forbidden_response,
            404: not_found_response,
        },
    ),
    destroy=extend_schema(
        description=(
            "Exclui definitivamente obra da organização ativa. "
            "Exige role OWNER ou ADMIN e CSRF."
        ),
        parameters=[csrf_header],
        responses={
            204: OpenApiResponse(description="Obra excluída; sem corpo de resposta."),
            403: forbidden_response,
            404: not_found_response,
        },
    ),
)
class ProjectViewSet(ModelViewSet):
    serializer_class = ProjectSerializer
    permission_classes = [
        IsAuthenticated,
        HasActiveOrganization,
        IsOrganizationAdminOrReadOnly,
    ]
    pagination_class = ProjectPagination
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    filter_backends = []

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Project.objects.none()
        return Project.objects.filter(organization=self.request.organization).order_by(
            "name", "id"
        )

    def perform_create(self, serializer):
        serializer.save(organization=self.request.organization)

from django.shortcuts import get_object_or_404
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
from apps.projects.models import Project

from ..models import BudgetItem
from .serializers import BudgetItemSerializer

csrf_header = OpenApiParameter(
    name="X-CSRFToken",
    location=OpenApiParameter.HEADER,
    type=OpenApiTypes.STR,
    required=True,
    description="Token CSRF atual; envie também os cookies csrftoken e sessionid.",
)
forbidden_response = OpenApiResponse(
    response=OpenApiTypes.OBJECT,
    description="Sessão/contexto inválido, falha CSRF ou escrita sem role OWNER/ADMIN.",
)
not_found_response = OpenApiResponse(
    response=OpenApiTypes.OBJECT,
    description="Project fora do tenant/inexistente ou item fora do Project da URL/inexistente.",
)
invalid_response = OpenApiResponse(
    response=OpenApiTypes.OBJECT,
    description="Campos inválidos, etapa indisponível ou decimais fora dos limites/precisão permitidos.",
)


@method_decorator(never_cache, name="dispatch")
@extend_schema(
    tags=["budgets"],
    parameters=[
        OpenApiParameter(
            name="project_id",
            location=OpenApiParameter.PATH,
            type=OpenApiTypes.INT,
            required=True,
            description="Project pertencente ao tenant ativo, definido exclusivamente pela URL.",
        )
    ],
)
@extend_schema_view(
    list=extend_schema(
        description="Itens previstos do Project, em coleção plana sem paginação. Ordem stage_id, id. Leitura para Membership ativa; sem filtros ou resumo agregado.",
        responses={
            200: BudgetItemSerializer(many=True),
            403: forbidden_response,
            404: not_found_response,
        },
    ),
    retrieve=extend_schema(
        description="Consulta item apenas dentro do Project da URL e tenant ativo. Total calculado, nunca persistido.",
        responses={
            200: BudgetItemSerializer,
            403: forbidden_response,
            404: not_found_response,
        },
    ),
    create=extend_schema(
        description="Cria item na etapa do Project validado. Exige stage_id, description, unit, quantity > 0 e unit_price >= 0. Envie decimais como strings; quantidade com até 4 casas e preço com até 2. total é somente leitura; campos extras project/organization são ignorados. Exige OWNER/ADMIN e CSRF.",
        request=BudgetItemSerializer,
        parameters=[csrf_header],
        responses={
            201: BudgetItemSerializer,
            400: invalid_response,
            403: forbidden_response,
            404: not_found_response,
        },
    ),
    partial_update=extend_schema(
        description="Altera campos do item, permitindo trocar stage_id somente dentro do mesmo Project. Stage omitida é preservada. Total é recalculado e não controlável pelo payload. Não altera Planning. Exige OWNER/ADMIN e CSRF.",
        request=BudgetItemSerializer,
        parameters=[csrf_header],
        responses={
            200: BudgetItemSerializer,
            400: invalid_response,
            403: forbidden_response,
            404: not_found_response,
        },
    ),
    destroy=extend_schema(
        description="Exclui somente o item, preservando ProjectStage e StagePlan. Exige OWNER/ADMIN e CSRF.",
        parameters=[csrf_header],
        responses={
            204: OpenApiResponse(description="Item excluído; sem corpo."),
            403: forbidden_response,
            404: not_found_response,
        },
    ),
)
class BudgetItemViewSet(ModelViewSet):
    serializer_class = BudgetItemSerializer
    permission_classes = [
        IsAuthenticated,
        HasActiveOrganization,
        IsOrganizationAdminOrReadOnly,
    ]
    pagination_class = None
    filter_backends = []
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_project(self):
        if not hasattr(self, "_project"):
            queryset = Project.objects.filter(organization=self.request.organization)
            self._project = get_object_or_404(queryset, pk=self.kwargs["project_id"])
        return self._project

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return BudgetItem.objects.none()
        return BudgetItem.objects.filter(stage__project=self.get_project()).order_by(
            "stage_id", "id"
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if not getattr(self, "swagger_fake_view", False):
            context["project"] = self.get_project()
        return context

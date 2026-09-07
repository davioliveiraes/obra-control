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
from rest_framework import mixins
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import GenericViewSet

from apps.organizations.permissions import (
    HasActiveOrganization,
    IsOrganizationAdminOrReadOnly,
)
from apps.projects.models import Project

from ..models import Expense
from .pagination import ExpensePagination
from .serializers import ExpenseSerializer

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
    description="Project fora do tenant/inexistente ou despesa fora do Project da URL/inexistente.",
)
invalid_response = OpenApiResponse(
    response=OpenApiTypes.OBJECT,
    description="Campos inválidos, etapa indisponível ou valor fora dos limites/precisão permitidos.",
)


@method_decorator(never_cache, name="dispatch")
@extend_schema(
    tags=["expenses"],
    parameters=[
        OpenApiParameter(
            name="project_id",
            location=OpenApiParameter.PATH,
            type=OpenApiTypes.INT,
            required=True,
            description="Project do tenant ativo, definido somente pela URL.",
        )
    ],
)
@extend_schema_view(
    list=extend_schema(
        description="Despesas do Project, inclusive canceladas. Páginas fixas de 25, ordem -expense_date, -id. Leitura para Membership ativa; sem filtros ou agregação.",
        responses={
            200: ExpenseSerializer(many=True),
            403: forbidden_response,
            404: not_found_response,
        },
    ),
    retrieve=extend_schema(
        description="Consulta despesa somente dentro do Project da URL e tenant ativo.",
        responses={
            200: ExpenseSerializer,
            403: forbidden_response,
            404: not_found_response,
        },
    ),
    create=extend_schema(
        description="Registra realizado financeiro. Exige description, amount > 0 e expense_date. stage_id opcional/nullable e do mesmo Project. Status padrão active. Amount é decimal com até 2 casas; envie string. Campos extras project/organization são ignorados. Exige OWNER/ADMIN e CSRF; não altera Budget ou Planning.",
        request=ExpenseSerializer,
        parameters=[csrf_header],
        responses={
            201: ExpenseSerializer,
            400: invalid_response,
            403: forbidden_response,
            404: not_found_response,
        },
    ),
    partial_update=extend_schema(
        description="Altera stage_id, description, amount, expense_date, status e notes. Não move Project. Stage omitida é preservada; null remove o vínculo. Cancelar preserva registro, valor e etapa. Sem DELETE/PUT ou reversão automática. Exige OWNER/ADMIN e CSRF.",
        request=ExpenseSerializer,
        parameters=[csrf_header],
        responses={
            200: ExpenseSerializer,
            400: invalid_response,
            403: forbidden_response,
            404: not_found_response,
        },
    ),
)
class ExpenseViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    GenericViewSet,
):
    serializer_class = ExpenseSerializer
    permission_classes = [
        IsAuthenticated,
        HasActiveOrganization,
        IsOrganizationAdminOrReadOnly,
    ]
    pagination_class = ExpensePagination
    filter_backends = []
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_project(self):
        if not hasattr(self, "_project"):
            queryset = Project.objects.filter(organization=self.request.organization)
            self._project = get_object_or_404(queryset, pk=self.kwargs["project_id"])
        return self._project

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Expense.objects.none()
        return Expense.objects.filter(project=self.get_project()).order_by(
            "-expense_date", "-id"
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if not getattr(self, "swagger_fake_view", False):
            context["project"] = self.get_project()
        return context

    def perform_create(self, serializer):
        serializer.save(project=self.get_project())

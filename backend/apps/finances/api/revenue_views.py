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

from ..models import Revenue
from .pagination import RevenuePagination
from .revenue_serializers import RevenueSerializer

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
    description="Project fora do tenant/inexistente ou receita fora do Project da URL/inexistente.",
)
invalid_response = OpenApiResponse(
    response=OpenApiTypes.OBJECT,
    description="Campos inválidos ou valor fora dos limites/precisão permitidos.",
)


@method_decorator(never_cache, name="dispatch")
@extend_schema(
    tags=["revenues"],
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
        description="Receitas realizadas do Project, inclusive canceladas. Páginas fixas de 25, ordem -revenue_date, -id. Leitura para Membership ativa; sem filtros ou agregação.",
        responses={
            200: RevenueSerializer(many=True),
            403: forbidden_response,
            404: not_found_response,
        },
    ),
    retrieve=extend_schema(
        description="Consulta receita somente dentro do Project da URL e tenant ativo.",
        responses={
            200: RevenueSerializer,
            403: forbidden_response,
            404: not_found_response,
        },
    ),
    create=extend_schema(
        description="Registra entrada realizada, não contas a receber. Exige description, amount > 0 e revenue_date. Status padrão active. Amount é string decimal com até 2 casas. Campos extras project/organization são ignorados. Exige OWNER/ADMIN e CSRF. Não altera Expense ou Cost Summary.",
        request=RevenueSerializer,
        parameters=[csrf_header],
        responses={
            201: RevenueSerializer,
            400: invalid_response,
            403: forbidden_response,
            404: not_found_response,
        },
    ),
    partial_update=extend_schema(
        description="Altera description, amount, revenue_date, status e notes. Não move Project. Cancelamento preserva registro, valor e Project, sem reversão automática. Sem DELETE/PUT. Exige OWNER/ADMIN e CSRF.",
        request=RevenueSerializer,
        parameters=[csrf_header],
        responses={
            200: RevenueSerializer,
            400: invalid_response,
            403: forbidden_response,
            404: not_found_response,
        },
    ),
)
class RevenueViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    GenericViewSet,
):
    serializer_class = RevenueSerializer
    permission_classes = [
        IsAuthenticated,
        HasActiveOrganization,
        IsOrganizationAdminOrReadOnly,
    ]
    pagination_class = RevenuePagination
    filter_backends = []
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_project(self):
        if not hasattr(self, "_project"):
            queryset = Project.objects.filter(organization=self.request.organization)
            self._project = get_object_or_404(queryset, pk=self.kwargs["project_id"])
        return self._project

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Revenue.objects.none()
        return Revenue.objects.filter(project=self.get_project()).order_by(
            "-revenue_date", "-id"
        )

    def perform_create(self, serializer):
        serializer.save(project=self.get_project())

    def create(self, request, *args, **kwargs):
        # Resolve the authorized URL Project before validating the submitted fields.
        self.get_project()
        return super().create(request, *args, **kwargs)

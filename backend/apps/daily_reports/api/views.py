from django.db import IntegrityError, transaction
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
from psycopg.errors import UniqueViolation
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from apps.organizations.permissions import (
    HasActiveOrganization,
    IsOrganizationAdminOrReadOnly,
)
from apps.projects.models import Project

from ..models import DAILY_REPORT_DATE_CONSTRAINT, DailyReport
from .pagination import DailyReportPagination
from .serializers import DUPLICATE_REPORT_MESSAGE, DailyReportSerializer

csrf_header = OpenApiParameter(
    name="X-CSRFToken",
    location=OpenApiParameter.HEADER,
    type=OpenApiTypes.STR,
    required=True,
    description="Token CSRF atual; envie também os cookies csrftoken e sessionid.",
)
project_parameter = OpenApiParameter(
    name="project_id",
    location=OpenApiParameter.PATH,
    type=OpenApiTypes.INT,
    required=True,
    description="Obra da organização ativa, definida exclusivamente pela URL.",
)
forbidden_response = OpenApiResponse(
    response=OpenApiTypes.OBJECT,
    description="Sessão/contexto inválido, falha CSRF ou escrita sem OWNER/ADMIN.",
)
not_found_response = OpenApiResponse(
    response=OpenApiTypes.OBJECT,
    description="Recurso inexistente ou fora da obra/RDO/tenant da URL.",
)
invalid_response = OpenApiResponse(
    response=OpenApiTypes.OBJECT,
    description="Campos inválidos ou já existe um RDO para a obra nesta data.",
)


@method_decorator(never_cache, name="dispatch")
@extend_schema(tags=["daily-reports"], parameters=[project_parameter])
@extend_schema_view(
    list=extend_schema(
        description="RDOs da obra, 25 por página, ordem -report_date, -id. Leitura para Membership ativa; sem atividades aninhadas.",
        responses={
            200: DailyReportSerializer(many=True),
            403: forbidden_response,
            404: not_found_response,
        },
    ),
    retrieve=extend_schema(
        responses={
            200: DailyReportSerializer,
            403: forbidden_response,
            404: not_found_response,
        },
    ),
    create=extend_schema(
        description="Cria RDO na obra da URL, inclusive retroativo. Um RDO por obra/data. Sem nested writes; campos extras de contexto são ignorados. Exige OWNER/ADMIN e CSRF.",
        parameters=[csrf_header],
        responses={
            201: DailyReportSerializer,
            400: invalid_response,
            403: forbidden_response,
            404: not_found_response,
        },
    ),
    partial_update=extend_schema(
        description="Altera data e observações, sem mover a obra. Duplicidade de data retorna 400. Exige OWNER/ADMIN e CSRF.",
        parameters=[csrf_header],
        responses={
            200: DailyReportSerializer,
            400: invalid_response,
            403: forbidden_response,
            404: not_found_response,
        },
    ),
    destroy=extend_schema(
        description="Exclui explicitamente o RDO e suas atividades; preserva a obra. Exige OWNER/ADMIN e CSRF.",
        parameters=[csrf_header],
        responses={
            204: OpenApiResponse(description="RDO e atividades excluídos."),
            403: forbidden_response,
            404: not_found_response,
        },
    ),
)
class DailyReportViewSet(ModelViewSet):
    serializer_class = DailyReportSerializer
    permission_classes = [
        IsAuthenticated,
        HasActiveOrganization,
        IsOrganizationAdminOrReadOnly,
    ]
    pagination_class = DailyReportPagination
    filter_backends = []
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_project(self):
        if not hasattr(self, "_project"):
            self._project = get_object_or_404(
                Project.objects.filter(organization=self.request.organization),
                pk=self.kwargs["project_id"],
            )
        return self._project

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return DailyReport.objects.none()
        return DailyReport.objects.filter(project=self.get_project()).order_by(
            "-report_date", "-id"
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if not getattr(self, "swagger_fake_view", False):
            context["project"] = self.get_project()
        return context

    def perform_create(self, serializer):
        self._save_report(serializer, project=self.get_project())

    def perform_update(self, serializer):
        self._save_report(serializer)

    def _save_report(self, serializer, **kwargs):
        try:
            with transaction.atomic():
                serializer.save(**kwargs)
        except IntegrityError as error:
            # Concurrent requests may both pass validation. Translate only this UNIQUE.
            if (
                isinstance(error.__cause__, UniqueViolation)
                and error.__cause__.diag.constraint_name == DAILY_REPORT_DATE_CONSTRAINT
            ):
                raise ValidationError(
                    {"report_date": [DUPLICATE_REPORT_MESSAGE]}
                ) from error
            raise

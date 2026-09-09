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

from ..models import DailyReport, DailyReportActivity
from .serializers import DailyReportActivitySerializer
from .views import (
    csrf_header,
    forbidden_response,
    not_found_response,
    project_parameter,
)

invalid_response = OpenApiResponse(
    response=OpenApiTypes.OBJECT,
    description="Campos inválidos ou etapa indisponível nesta obra.",
)


@method_decorator(never_cache, name="dispatch")
@extend_schema(
    tags=["daily-reports"],
    parameters=[
        project_parameter,
        OpenApiParameter(
            name="report_id",
            location=OpenApiParameter.PATH,
            type=OpenApiTypes.INT,
            required=True,
            description="RDO pertencente à obra da URL.",
        ),
    ],
)
@extend_schema_view(
    list=extend_schema(
        description="Atividades do RDO, coleção plana sem paginação; ordem position, id. Leitura para Membership ativa.",
        responses={
            200: DailyReportActivitySerializer(many=True),
            403: forbidden_response,
            404: not_found_response,
        },
    ),
    retrieve=extend_schema(
        responses={
            200: DailyReportActivitySerializer,
            403: forbidden_response,
            404: not_found_response,
        }
    ),
    create=extend_schema(
        description="Cria atividade no RDO da URL. stage_id opcional/nullable, restrito à mesma obra. Sem nested writes. Exige OWNER/ADMIN e CSRF.",
        parameters=[csrf_header],
        responses={
            201: DailyReportActivitySerializer,
            400: invalid_response,
            403: forbidden_response,
            404: not_found_response,
        },
    ),
    partial_update=extend_schema(
        description="Altera descrição, posição e etapa opcional da mesma obra; não move o RDO. Exige OWNER/ADMIN e CSRF.",
        parameters=[csrf_header],
        responses={
            200: DailyReportActivitySerializer,
            400: invalid_response,
            403: forbidden_response,
            404: not_found_response,
        },
    ),
    destroy=extend_schema(
        description="Exclui somente a atividade, preservando RDO e etapa. Exige OWNER/ADMIN e CSRF.",
        parameters=[csrf_header],
        responses={
            204: OpenApiResponse(description="Atividade excluída."),
            403: forbidden_response,
            404: not_found_response,
        },
    ),
)
class DailyReportActivityViewSet(ModelViewSet):
    serializer_class = DailyReportActivitySerializer
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
            self._project = get_object_or_404(
                Project.objects.filter(organization=self.request.organization),
                pk=self.kwargs["project_id"],
            )
        return self._project

    def get_report(self):
        if not hasattr(self, "_report"):
            self._report = get_object_or_404(
                DailyReport.objects.filter(project=self.get_project()),
                pk=self.kwargs["report_id"],
            )
        return self._report

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return DailyReportActivity.objects.none()
        return DailyReportActivity.objects.filter(
            daily_report=self.get_report()
        ).order_by("position", "id")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if not getattr(self, "swagger_fake_view", False):
            self.get_report()
            context["project"] = self.get_project()
        return context

    def perform_create(self, serializer):
        serializer.save(daily_report=self.get_report())

from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.organizations.permissions import (
    HasActiveOrganization,
    IsOrganizationAdminOrReadOnly,
)
from apps.projects.models import Project

from ..services.financial_summary import get_project_financial_summary
from .financial_summary_serializers import ProjectFinancialSummarySerializer


@method_decorator(never_cache, name="dispatch")
class ProjectFinancialSummaryView(APIView):
    permission_classes = [
        IsAuthenticated,
        HasActiveOrganization,
        IsOrganizationAdminOrReadOnly,
    ]
    http_method_names = ["get", "head", "options"]

    @extend_schema(
        tags=["financial-summary"],
        description=(
            "Resumo realizado acumulado da obra no tenant ativo, somente leitura. "
            "revenue_total soma Revenue ACTIVE; expense_total soma Expense ACTIVE, "
            "com ou sem Stage. Registros CANCELED são ignorados. "
            "realized_balance = revenue_total - expense_total; saldo negativo é válido. "
            "Valores são strings decimais com duas casas; ausência de dados retorna 0.00. "
            "Sem filtros temporais, paginação ou participação de Budget/Planning/EAP. "
            "OWNER/ADMIN/MEMBER podem consultar com contexto ativo; GET não exige CSRF. "
            "O saldo realizado não representa lucro contábil, DRE ou saldo bancário."
        ),
        parameters=[
            OpenApiParameter(
                name="project_id",
                location=OpenApiParameter.PATH,
                type=OpenApiTypes.INT,
                required=True,
                description="Project pertencente à organização ativa.",
            )
        ],
        responses={
            200: ProjectFinancialSummarySerializer,
            403: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description="Sessão ou contexto organizacional ausente/inválido.",
            ),
            404: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description="Project inexistente ou fora do tenant ativo.",
            ),
        },
    )
    def get(self, request, project_id):
        project = get_object_or_404(
            Project.objects.filter(organization=request.organization), pk=project_id
        )
        summary = get_project_financial_summary(project)
        return Response(ProjectFinancialSummarySerializer(summary).data)

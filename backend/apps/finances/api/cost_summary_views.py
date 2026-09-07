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

from ..services.cost_summary import get_project_cost_summary
from .cost_summary_serializers import CostSummarySerializer


@method_decorator(never_cache, name="dispatch")
class CostSummaryView(APIView):
    permission_classes = [
        IsAuthenticated,
        HasActiveOrganization,
        IsOrganizationAdminOrReadOnly,
    ]
    http_method_names = ["get", "head", "options"]

    @extend_schema(
        tags=["cost-summary"],
        description=(
            "Resumo acumulado de custos do Project no tenant ativo, somente leitura. "
            "Previsto soma cada BudgetItem arredondado para 2 casas com ROUND_HALF_UP. "
            "Realizado inclui somente Expense ACTIVE; CANCELED é ignorada. "
            "Despesas sem Stage entram no actual_total geral e unallocated_actual_total, "
            "não nas linhas de Stage. Valores por Stage são diretos, sem roll-up de filhos, "
            "em ordem position, id. variance_amount = budget_total - actual_total. "
            "Sem paginação, filtros temporais, percentuais ou uso de Planning. "
            "OWNER/ADMIN/MEMBER podem consultar com sessão e contexto ativo; GET não exige CSRF."
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
            200: CostSummarySerializer,
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
        summary = get_project_cost_summary(project)
        return Response(CostSummarySerializer(summary).data)

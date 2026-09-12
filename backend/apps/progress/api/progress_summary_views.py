from django.shortcuts import get_object_or_404
from django.utils import timezone
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

from ..services.progress_summary import get_project_progress_summary
from .progress_summary_serializers import ProjectProgressSummarySerializer


@method_decorator(never_cache, name="dispatch")
class ProjectProgressSummaryView(APIView):
    permission_classes = [
        IsAuthenticated,
        HasActiveOrganization,
        IsOrganizationAdminOrReadOnly,
    ]
    http_method_names = ["get", "head", "options"]

    @extend_schema(
        tags=["progress-summary"],
        description=(
            "Progresso físico direto por etapa, somente leitura no tenant ativo. "
            "as_of_date é a data local do servidor (timezone Django America/Fortaleza), "
            "calculada uma vez; não há filtro público de data. Seleciona por etapa "
            "o primeiro apontamento em ordem -progress_date, -id, com "
            "progress_date <= as_of_date. Apontamentos futuros são excluídos. "
            "Cadastro/edição e maior percentual não determinam o último apontamento. "
            "Todas as etapas aparecem em ordem position, id, sem paginação. "
            "Sem apontamento elegível, ID/data/percentual são null; zero informado "
            "é a string 0.00. Sem progresso global, médias, pesos ou roll-up. "
            "Correções/exclusões do histórico afetam consultas seguintes. "
            "OWNER/ADMIN/MEMBER podem consultar com sessão e contexto ativos; "
            "GET não exige CSRF. Resposta no-store; não há métodos de escrita."
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
            200: ProjectProgressSummarySerializer,
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
        as_of_date = timezone.localdate()
        summary = get_project_progress_summary(project, as_of_date=as_of_date)
        return Response(ProjectProgressSummarySerializer(summary).data)

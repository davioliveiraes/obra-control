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
from apps.projects.models import Project, ProjectStage

from ..models import STAGE_PROGRESS_DATE_CONSTRAINT, StageProgressEntry
from .pagination import StageProgressEntryPagination
from .serializers import DUPLICATE_PROGRESS_MESSAGE, StageProgressEntrySerializer

csrf_header = OpenApiParameter(
    name="X-CSRFToken",
    type=OpenApiTypes.STR,
    location=OpenApiParameter.HEADER,
    required=True,
    description="Token CSRF atual; envie também os cookies csrftoken e sessionid.",
)
forbidden_response = OpenApiResponse(
    response=OpenApiTypes.OBJECT,
    description="Sessão/contexto inválido, falha CSRF ou escrita sem OWNER/ADMIN.",
)
not_found_response = OpenApiResponse(
    response=OpenApiTypes.OBJECT,
    description="Recurso inexistente ou fora do tenant/Project/Stage da URL.",
)
invalid_response = OpenApiResponse(
    response=OpenApiTypes.OBJECT,
    description="Campos inválidos, percentual fora de 0..100 ou data já registrada na etapa.",
)


@method_decorator(never_cache, name="dispatch")
@extend_schema(
    tags=["stage-progress"],
    parameters=[
        OpenApiParameter(
            name="project_id",
            location=OpenApiParameter.PATH,
            type=OpenApiTypes.INT,
            required=True,
            description="Obra pertencente à organização ativa.",
        ),
        OpenApiParameter(
            name="stage_id",
            location=OpenApiParameter.PATH,
            type=OpenApiTypes.INT,
            required=True,
            description="Etapa pertencente à obra da URL; nunca escolhida pelo payload.",
        ),
    ],
)
@extend_schema_view(
    list=extend_schema(
        description="Histórico informado da etapa, 25 por página, ordem -progress_date, -id. Leitura para Membership ativa; sem roll-up ou progresso global.",
        responses={
            200: StageProgressEntrySerializer(many=True),
            403: forbidden_response,
            404: not_found_response,
        },
    ),
    retrieve=extend_schema(
        responses={
            200: StageProgressEntrySerializer,
            403: forbidden_response,
            404: not_found_response,
        }
    ),
    create=extend_schema(
        description="Registra percentual Decimal de 0.00 a 100.00, inclusive. Aceita datas retroativas/futuras e redução de percentual. Um registro por etapa/data, inclusive em concorrência. Campos extras de contexto são ignorados. Exige OWNER/ADMIN e CSRF.",
        parameters=[csrf_header],
        responses={
            201: StageProgressEntrySerializer,
            400: invalid_response,
            403: forbidden_response,
            404: not_found_response,
        },
    ),
    partial_update=extend_schema(
        description="Altera data, percentual ou notes, sem mover a etapa. Duplicidade de data retorna 400. Sem exigência de monotonicidade. Exige OWNER/ADMIN e CSRF.",
        parameters=[csrf_header],
        responses={
            200: StageProgressEntrySerializer,
            400: invalid_response,
            403: forbidden_response,
            404: not_found_response,
        },
    ),
    destroy=extend_schema(
        description="Exclui explicitamente o apontamento, preservando Stage e Project. Exige OWNER/ADMIN e CSRF.",
        parameters=[csrf_header],
        responses={
            204: OpenApiResponse(description="Apontamento excluído; sem corpo."),
            403: forbidden_response,
            404: not_found_response,
        },
    ),
)
class StageProgressEntryViewSet(ModelViewSet):
    serializer_class = StageProgressEntrySerializer
    permission_classes = [
        IsAuthenticated,
        HasActiveOrganization,
        IsOrganizationAdminOrReadOnly,
    ]
    pagination_class = StageProgressEntryPagination
    filter_backends = []
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_project(self):
        if not hasattr(self, "_project"):
            self._project = get_object_or_404(
                Project.objects.filter(organization=self.request.organization),
                pk=self.kwargs["project_id"],
            )
        return self._project

    def get_stage(self):
        if not hasattr(self, "_stage"):
            self._stage = get_object_or_404(
                ProjectStage.objects.filter(project=self.get_project()),
                pk=self.kwargs["stage_id"],
            )
        return self._stage

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return StageProgressEntry.objects.none()
        return StageProgressEntry.objects.filter(stage=self.get_stage()).order_by(
            "-progress_date", "-id"
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if not getattr(self, "swagger_fake_view", False):
            context["stage"] = self.get_stage()
        return context

    def perform_create(self, serializer):
        self._save_entry(serializer, stage=self.get_stage())

    def perform_update(self, serializer):
        self._save_entry(serializer)

    def _save_entry(self, serializer, **kwargs):
        try:
            with transaction.atomic():
                serializer.save(**kwargs)
        except IntegrityError as error:
            # Concurrent requests may pass validation together. Roll back first and
            # translate only the known stage/date UNIQUE, not unrelated DB errors.
            if (
                isinstance(error.__cause__, UniqueViolation)
                and error.__cause__.diag.constraint_name
                == STAGE_PROGRESS_DATE_CONSTRAINT
            ):
                raise ValidationError(
                    {"progress_date": [DUPLICATE_PROGRESS_MESSAGE]}
                ) from error
            raise

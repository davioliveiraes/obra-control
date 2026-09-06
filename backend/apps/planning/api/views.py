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

from ..models import StagePlan
from .serializers import (
    DUPLICATE_PLAN_MESSAGE,
    StagePlanCreateSerializer,
    StagePlanSerializer,
)

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
    description="Project fora do tenant/inexistente ou planejamento fora do Project da URL/inexistente.",
)
invalid_response = OpenApiResponse(
    response=OpenApiTypes.OBJECT,
    description="Campos inválidos, datas invertidas, etapa indisponível ou já planejada.",
)


@method_decorator(never_cache, name="dispatch")
@extend_schema(
    tags=["planning"],
    parameters=[
        OpenApiParameter(
            name="project_id",
            location=OpenApiParameter.PATH,
            type=OpenApiTypes.INT,
            required=True,
            description="Project pertencente à organização ativa, definido somente pela URL.",
        )
    ],
)
@extend_schema_view(
    list=extend_schema(
        description="Planejamento completo e plano do Project, sem paginação. Ordem stage__position, stage_id. Leitura para Membership ativa.",
        responses={
            200: StagePlanSerializer(many=True),
            403: forbidden_response,
            404: not_found_response,
        },
    ),
    retrieve=extend_schema(
        description="Consulta planejamento somente dentro do Project da URL e tenant ativo.",
        responses={
            200: StagePlanSerializer,
            403: forbidden_response,
            404: not_found_response,
        },
    ),
    create=extend_schema(
        description="Planeja uma etapa do mesmo Project. stage_id e ambas as datas são obrigatórios; fim >= início. Duplicidade retorna 400, inclusive em concorrência. Campos extras project/organization são ignorados. Exige OWNER/ADMIN e CSRF.",
        request=StagePlanCreateSerializer,
        parameters=[csrf_header],
        responses={
            201: StagePlanSerializer,
            400: invalid_response,
            403: forbidden_response,
            404: not_found_response,
        },
    ),
    partial_update=extend_schema(
        description="Altera somente datas, combinadas com os valores persistidos para validar fim >= início. stage_id é somente leitura; campos extras stage/project/organization são ignorados. Exige OWNER/ADMIN e CSRF.",
        request=StagePlanSerializer,
        parameters=[csrf_header],
        responses={
            200: StagePlanSerializer,
            400: invalid_response,
            403: forbidden_response,
            404: not_found_response,
        },
    ),
    destroy=extend_schema(
        description="Exclui somente o planejamento, preservando a etapa da EAP. Exige OWNER/ADMIN e CSRF.",
        parameters=[csrf_header],
        responses={
            204: OpenApiResponse(description="Planejamento excluído; sem corpo."),
            403: forbidden_response,
            404: not_found_response,
        },
    ),
)
class StagePlanViewSet(ModelViewSet):
    serializer_class = StagePlanSerializer
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
            return StagePlan.objects.none()
        return StagePlan.objects.filter(stage__project=self.get_project()).order_by(
            "stage__position", "stage_id"
        )

    def get_serializer_class(self):
        if self.action == "create":
            return StagePlanCreateSerializer
        return StagePlanSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if not getattr(self, "swagger_fake_view", False):
            context["project"] = self.get_project()
        return context

    def perform_create(self, serializer):
        try:
            with transaction.atomic():
                serializer.save()
        except IntegrityError as error:
            # Roll back before querying; concurrent POSTs can both pass validation.
            if (
                isinstance(error.__cause__, UniqueViolation)
                and StagePlan.objects.filter(
                    stage=serializer.validated_data["stage"]
                ).exists()
            ):
                raise ValidationError({"stage_id": [DUPLICATE_PLAN_MESSAGE]}) from error
            raise

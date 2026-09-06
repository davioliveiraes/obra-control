from django.db import transaction
from django.db.models.deletion import RestrictedError
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
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.organizations.permissions import (
    HasActiveOrganization,
    IsOrganizationAdminOrReadOnly,
)

from ..models import Project, ProjectStage
from .stage_serializers import ProjectStageSerializer
from .views import csrf_header, forbidden_response

not_found_response = OpenApiResponse(
    response=OpenApiTypes.OBJECT,
    description="Project fora do tenant/inexistente ou etapa fora do Project da URL/inexistente.",
)
invalid_response = OpenApiResponse(
    response=OpenApiTypes.OBJECT,
    description="Campos inválidos, parent indisponível, self-parent ou ciclo; nada é gravado.",
)


@method_decorator(never_cache, name="dispatch")
@extend_schema(
    tags=["project-stages"],
    parameters=[
        OpenApiParameter(
            name="project_id",
            location=OpenApiParameter.PATH,
            type=OpenApiTypes.INT,
            required=True,
            description="Project pertencente à organização ativa; nunca escolhido pelo payload.",
        )
    ],
)
@extend_schema_view(
    list=extend_schema(
        description="EAP plana completa, sem paginação ou children recursivos. Ordem position, id. Leitura para Membership ativa.",
        responses={
            200: ProjectStageSerializer(many=True),
            403: forbidden_response,
            404: not_found_response,
        },
    ),
    retrieve=extend_schema(
        description="Consulta etapa somente dentro do Project da URL e do tenant ativo.",
        responses={
            200: ProjectStageSerializer,
            403: forbidden_response,
            404: not_found_response,
        },
    ),
    create=extend_schema(
        description="Cria etapa no Project validado da URL. parent_id opcional e do mesmo Project. Campos extras project/organization são ignorados. Exige OWNER/ADMIN e CSRF.",
        request=ProjectStageSerializer,
        parameters=[csrf_header],
        responses={
            201: ProjectStageSerializer,
            400: invalid_response,
            403: forbidden_response,
            404: not_found_response,
        },
    ),
    partial_update=extend_schema(
        description="Altera name, description, parent_id ou position. Não transfere Project; bloqueia self-parent e ciclos. Exige OWNER/ADMIN e CSRF.",
        request=ProjectStageSerializer,
        parameters=[csrf_header],
        responses={
            200: ProjectStageSerializer,
            400: invalid_response,
            403: forbidden_response,
            404: not_found_response,
        },
    ),
    destroy=extend_schema(
        description="Exclui somente uma etapa sem filhos. Exige OWNER/ADMIN e CSRF.",
        parameters=[csrf_header],
        responses={
            204: OpenApiResponse(description="Etapa excluída; sem corpo."),
            403: forbidden_response,
            404: not_found_response,
            409: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description="A etapa possui subetapas e não pode ser excluída.",
            ),
        },
    ),
)
class ProjectStageViewSet(ModelViewSet):
    serializer_class = ProjectStageSerializer
    permission_classes = [
        IsAuthenticated,
        HasActiveOrganization,
        IsOrganizationAdminOrReadOnly,
    ]
    pagination_class = None
    filter_backends = []
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_project(self, *, for_update=False):
        if for_update or not hasattr(self, "_project"):
            queryset = Project.objects.filter(organization=self.request.organization)
            if for_update:
                queryset = queryset.select_for_update()
            self._project = get_object_or_404(queryset, pk=self.kwargs["project_id"])
        return self._project

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ProjectStage.objects.none()
        return ProjectStage.objects.filter(project=self.get_project()).order_by(
            "position", "id"
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if not getattr(self, "swagger_fake_view", False):
            context["project"] = self.get_project()
        return context

    def perform_create(self, serializer):
        serializer.save(project=self.get_project())

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        # Serialize tree writes per project before reading ancestry or saving.
        self.get_project(for_update=True)
        return super().create(request, *args, **kwargs)

    @transaction.atomic
    def partial_update(self, request, *args, **kwargs):
        self.get_project(for_update=True)
        return super().partial_update(request, *args, **kwargs)

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        self.get_project(for_update=True)
        instance = self.get_object()
        try:
            self.perform_destroy(instance)
        except RestrictedError:
            return Response(
                {"detail": "A etapa possui subetapas e não pode ser excluída."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)

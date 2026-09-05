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

from apps.organizations.permissions import HasActiveOrganization

from ..models import Customer
from .pagination import CustomerPagination
from .serializers import CustomerSerializer

csrf_header = OpenApiParameter(
    name="X-CSRFToken",
    type=OpenApiTypes.STR,
    location=OpenApiParameter.HEADER,
    required=True,
    description="Token CSRF atual; envie também os cookies csrftoken e sessionid.",
)
forbidden_response = OpenApiResponse(
    response=OpenApiTypes.OBJECT,
    description="Sessão ausente/inválida, contexto organizacional ausente ou falha CSRF.",
)
not_found_response = OpenApiResponse(
    response=OpenApiTypes.OBJECT,
    description="Cliente não encontrado na organização atual, inclusive IDs de outro tenant.",
)
invalid_response = OpenApiResponse(
    response=OpenApiTypes.OBJECT,
    description="Campos inválidos; nome não pode ser vazio.",
)


@method_decorator(never_cache, name="dispatch")
@extend_schema(tags=["customers"])
@extend_schema_view(
    list=extend_schema(
        description=(
            "Lista somente clientes da organização ativa. Paginação fixa de 25 itens, "
            "ordenados por name e id. Exige sessão e Membership ativa; sem distinção de roles."
        ),
        responses={200: CustomerSerializer(many=True), 403: forbidden_response},
    ),
    create=extend_schema(
        description=(
            "Cria cliente na organização validada da request, nunca em tenant do payload. "
            "Campos organization/organization_id não pertencem ao contrato e são ignorados. "
            "Exige contexto ativo e CSRF."
        ),
        parameters=[csrf_header],
        request=CustomerSerializer,
        responses={
            201: CustomerSerializer,
            400: invalid_response,
            403: forbidden_response,
        },
    ),
    retrieve=extend_schema(
        description="Consulta cliente somente no queryset da organização ativa.",
        responses={
            200: CustomerSerializer,
            403: forbidden_response,
            404: not_found_response,
        },
    ),
    partial_update=extend_schema(
        description=(
            "Atualiza parcialmente cliente da organização ativa. Não permite transferir "
            "o cliente entre organizações. Exige CSRF."
        ),
        parameters=[csrf_header],
        request=CustomerSerializer,
        responses={
            200: CustomerSerializer,
            400: invalid_response,
            403: forbidden_response,
            404: not_found_response,
        },
    ),
    destroy=extend_schema(
        description="Exclui definitivamente cliente da organização ativa. Exige CSRF.",
        parameters=[csrf_header],
        responses={
            204: OpenApiResponse(
                description="Cliente excluído; sem corpo de resposta."
            ),
            403: forbidden_response,
            404: not_found_response,
        },
    ),
)
class CustomerViewSet(ModelViewSet):
    serializer_class = CustomerSerializer
    permission_classes = [IsAuthenticated, HasActiveOrganization]
    pagination_class = CustomerPagination
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    filter_backends = []

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Customer.objects.none()
        return Customer.objects.filter(organization=self.request.organization).order_by(
            "name", "id"
        )

    def perform_create(self, serializer):
        serializer.save(organization=self.request.organization)

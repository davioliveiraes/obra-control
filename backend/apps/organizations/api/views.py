from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..context import CURRENT_ORGANIZATION_SESSION_KEY, get_active_membership
from ..models import Membership
from .serializers import AccessibleOrganizationSerializer, SelectOrganizationSerializer

csrf_header = OpenApiParameter(
    name="X-CSRFToken",
    type=OpenApiTypes.STR,
    location=OpenApiParameter.HEADER,
    required=True,
    description="Token CSRF atual; envie também os cookies csrftoken e sessionid.",
)


@method_decorator(never_cache, name="dispatch")
class OrganizationListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["organizations"],
        responses={
            200: AccessibleOrganizationSerializer(many=True),
            403: OpenApiResponse(
                response=OpenApiTypes.OBJECT, description="Sessão ausente ou inválida."
            ),
        },
        description=(
            "Lista somente organizações com Membership ativa do usuário autenticado. "
            "Role é informativo, não uma regra de autorização. Não seleciona contexto."
        ),
    )
    def get(self, request):
        memberships = (
            Membership.objects.filter(user=request.user, is_active=True)
            .select_related("organization")
            .order_by("organization_id")
        )
        return Response(AccessibleOrganizationSerializer(memberships, many=True).data)


@method_decorator(never_cache, name="dispatch")
class CurrentOrganizationView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["organizations"],
        responses={
            200: AccessibleOrganizationSerializer,
            403: OpenApiResponse(
                response=OpenApiTypes.OBJECT, description="Sessão ausente ou inválida."
            ),
            404: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description='{"detail": "Nenhuma organização selecionada."}',
            ),
        },
        description=(
            "Consulta o contexto revalidado pelo middleware. Sem seleção ou após "
            "revogação da Membership, retorna 404. Não escolhe organização automaticamente."
        ),
    )
    def get(self, request):
        if request.membership is None:
            return Response(
                {"detail": "Nenhuma organização selecionada."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(AccessibleOrganizationSerializer(request.membership).data)

    @extend_schema(
        tags=["organizations"],
        request=SelectOrganizationSerializer,
        parameters=[csrf_header],
        responses={
            200: AccessibleOrganizationSerializer,
            400: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description="Contrato de seleção inválido.",
            ),
            403: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description=(
                    'Sem Membership ativa: {"detail": "Organização indisponível."}. '
                    "Não distingue organização inexistente, alheia ou vínculo inativo. "
                    "Também retornado para sessão inválida ou falha CSRF."
                ),
            ),
        },
        description=(
            "Seleciona uma organização mediante Membership ativa do usuário. "
            "Armazena apenas current_organization_id na sessão. Uma seleção negada "
            "preserva o contexto anterior se ele ainda for válido. Exige CSRF."
        ),
    )
    def put(self, request):
        serializer = SelectOrganizationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        membership = get_active_membership(
            request.user, serializer.validated_data["organization_id"]
        )
        if membership is None:
            return Response(
                {"detail": "Organização indisponível."},
                status=status.HTTP_403_FORBIDDEN,
            )
        request.session[CURRENT_ORGANIZATION_SESSION_KEY] = membership.organization_id
        return Response(AccessibleOrganizationSerializer(membership).data)

    @extend_schema(
        tags=["organizations"],
        request=None,
        parameters=[csrf_header],
        responses={
            204: OpenApiResponse(
                description="Seleção removida; usuário segue autenticado."
            ),
            403: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description="Sessão ausente/inválida ou falha CSRF.",
            ),
        },
        description="Remove somente a seleção de organização, sem logout. Exige CSRF.",
    )
    def delete(self, request):
        request.session.pop(CURRENT_ORGANIZATION_SESSION_KEY, None)
        return Response(status=status.HTTP_204_NO_CONTENT)

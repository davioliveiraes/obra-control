from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import CsrfTokenSerializer, LoginSerializer, UserIdentitySerializer

csrf_header = OpenApiParameter(
    name="X-CSRFToken",
    type=OpenApiTypes.STR,
    location=OpenApiParameter.HEADER,
    required=True,
    description="Token obtido em /api/v1/auth/csrf/; envie também o cookie csrftoken.",
)


@method_decorator(never_cache, name="dispatch")
class CsrfView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["auth"],
        auth=[],
        responses={200: CsrfTokenSerializer},
        description=(
            "Inicializa o cookie CSRF e retorna um token mascarado nativo do Django. "
            "Preserve os cookies e envie o token em X-CSRFToken nos POSTs. "
            "Após login, obtenha um novo token, pois o Django rotaciona o CSRF."
        ),
    )
    def get(self, request):
        # get_token() asks CsrfViewMiddleware to set the cookie on the response.
        return Response({"csrfToken": get_token(request)})


@method_decorator(never_cache, name="dispatch")
@method_decorator(csrf_protect, name="dispatch")
@method_decorator(sensitive_post_parameters("password"), name="dispatch")
class LoginView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["auth"],
        auth=[],
        request=LoginSerializer,
        parameters=[csrf_header],
        responses={
            200: UserIdentitySerializer,
            400: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description=(
                    "Erros de validação por campo, ou "
                    '{"detail": "Credenciais inválidas."} para credenciais rejeitadas, '
                    "incluindo usuário inativo."
                ),
            ),
            (403, "text/html"): OpenApiResponse(
                response=OpenApiTypes.STR,
                description="Rejeição CSRF pelo Django, inclusive para anônimos.",
            ),
        },
        description=(
            "Autentica por email e senha, criando a sessão via cookie sessionid. "
            "Exige CSRF mesmo sem sessão prévia. Retorna somente identidade global; "
            "o cookie CSRF é rotacionado no login."
        ),
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(request=request, **serializer.validated_data)
        if user is None:
            return Response(
                {"detail": "Credenciais inválidas."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        login(request, user)
        return Response(UserIdentitySerializer(user).data)


@method_decorator(never_cache, name="dispatch")
class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["auth"],
        request=None,
        parameters=[csrf_header],
        responses={
            204: OpenApiResponse(
                description="Sessão encerrada, sem corpo de resposta."
            ),
            403: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description="Sessão ausente/inválida ou falha de CSRF.",
            ),
        },
        description="Encerra a sessão Django. Exige cookie de sessão e CSRF válido.",
    )
    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


@method_decorator(never_cache, name="dispatch")
class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["auth"],
        responses={
            200: UserIdentitySerializer,
            403: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description="Sessão ausente ou inválida.",
            ),
        },
        description="Retorna somente a identidade global reconhecida pela sessão Django.",
    )
    def get(self, request):
        return Response(UserIdentitySerializer(request.user).data)

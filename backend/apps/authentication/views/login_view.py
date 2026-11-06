from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema

from apps.authentication.services.authentication_service import AuthenticationService
from apps.authentication.serializers import (
    LoginRequestSerializer,
    LoginResponseSerializer
)


class LoginView(APIView):
    """
    Endpoint de login del usuario.
    Delega autenticación y generación de tokens a AuthenticationService.
    """
    authentication_classes = []
    permission_classes = []

    @extend_schema(
        summary="Login de usuario",
        description="Autenticación de usuario y generación de tokens JWT",
        request=LoginRequestSerializer,
        responses={
            200: LoginResponseSerializer,
            400: {"detail": "Usuario y contraseña requeridos"},
            401: {"detail": "Credenciales inválidas"},
        },
        auth=[],
    )
    def post(self, request):
        username = request.data.get("username")
        password = request.data.get("password")

        try:
            result = AuthenticationService.login(username, password, request)
        except ValueError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Crear respuesta con datos de usuario
        response = Response({
            "user": result["user"]
        })

        # Establecer tokens en cookies httpOnly (protección XSS)
        cookie_settings = AuthenticationService.get_secure_cookie_settings(request)

        response.set_cookie(
            key='access_token',
            value=result["access_token"],
            **cookie_settings,
            max_age=15 * 60  # 15 minutos
        )

        response.set_cookie(
            key='refresh_token',
            value=result["refresh_token"],
            **cookie_settings,
            max_age=7 * 24 * 60 * 60  # 7 días
        )

        return response

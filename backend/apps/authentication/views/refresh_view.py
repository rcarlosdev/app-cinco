# apps/authentication/views/refresh_views.py
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema

from apps.authentication.services.authentication_service import AuthenticationService
from apps.authentication.serializers import (
    RefreshTokenRequestSerializer,
    RefreshTokenResponseSerializer,
)


class RefreshTokenView(APIView):
    """
    Endpoint para renovar access token.
    Delega rotación de refresh token a AuthenticationService.
    """
    authentication_classes = []
    permission_classes = []

    @extend_schema(
        summary="Renovar token de acceso",
        description="Genera un nuevo access token rotando el refresh token",
        request=RefreshTokenRequestSerializer,
        responses={
            200: RefreshTokenResponseSerializer,
            400: {"detail": "refresh_token is required"},
            401: {"detail": "Invalid or expired refresh token"},
        },
        auth=[],
    )
    def post(self, request):
        # Leer refresh_token desde cookies
        refresh_token = request.COOKIES.get('refresh_token')

        try:
            tokens = AuthenticationService.refresh_tokens(refresh_token, request)
        except ValueError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Crear respuesta vacía (tokens van en cookies)
        response = Response({"detail": "Tokens refreshed successfully"}, status=status.HTTP_200_OK)

        # Establecer nuevos tokens en cookies
        cookie_settings = AuthenticationService.get_secure_cookie_settings(request)

        response.set_cookie(
            key='access_token',
            value=tokens['access_token'],
            **cookie_settings,
            max_age=15 * 60  # 15 minutos
        )

        response.set_cookie(
            key='refresh_token',
            value=tokens['refresh_token'],
            **cookie_settings,
            max_age=7 * 24 * 60 * 60  # 7 días
        )

        return response

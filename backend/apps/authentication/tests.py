from django.test import TestCase
from django.contrib.auth.models import User
from unittest.mock import patch, MagicMock

from apps.authentication.services.authentication_service import AuthenticationService


class AuthenticationServiceTestCase(TestCase):
    """
    Tests de regresión para AuthenticationService.
    Valida que la refactorización a clase estática preserva el comportamiento.
    """

    def setUp(self):
        """Prepara usuario de prueba."""
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="password123"
        )
        self.request = MagicMock()
        self.request.META.get.side_effect = lambda key, default=None: {
            'REMOTE_ADDR': '127.0.0.1',
            'HTTP_USER_AGENT': 'Mozilla/5.0',
            'HTTP_ACCEPT_LANGUAGE': 'en-US'
        }.get(key, default)

    @patch("apps.authentication.services.authentication_service.authenticate")
    @patch("apps.authentication.services.authentication_service.AuthenticationService._create_refresh_token")
    def test_login_valido(self, mock_create_refresh, mock_authenticate):
        """
        Verifica que login autentica usuario y retorna tokens.
        """
        mock_authenticate.return_value = self.user
        mock_refresh_token = MagicMock()
        mock_refresh_token.token = "refresh_token_123"
        mock_create_refresh.return_value = mock_refresh_token

        resultado = AuthenticationService.login("testuser", "password123", self.request)

        # Validar estructura de respuesta
        self.assertIn("user", resultado)
        self.assertIn("access_token", resultado)
        self.assertIn("refresh_token", resultado)
        self.assertEqual(resultado["user"]["username"], "testuser")
        self.assertEqual(resultado["user"]["id"], self.user.id)

    @patch("apps.authentication.services.authentication_service.authenticate")
    def test_login_credenciales_invalidas(self, mock_authenticate):
        """
        Verifica que login levanta ValueError con credenciales inválidas.
        """
        mock_authenticate.return_value = None

        with self.assertRaises(ValueError) as context:
            AuthenticationService.login("testuser", "wrongpassword", self.request)

        self.assertIn("Credenciales inválidas", str(context.exception))

    def test_login_parametros_faltantes(self):
        """
        Verifica que login levanta ValueError sin username o password.
        """
        with self.assertRaises(ValueError) as context:
            AuthenticationService.login(None, "password123", self.request)

        self.assertIn("Usuario y contraseña requeridos", str(context.exception))

    @patch("apps.authentication.services.authentication_service.rotate_refresh_token")
    def test_refresh_tokens_exitoso(self, mock_rotate):
        """
        Verifica que refresh_tokens rota token correctamente.
        """
        mock_rotate.return_value = {
            "access_token": "new_access_token",
            "refresh_token": "new_refresh_token"
        }

        resultado = AuthenticationService.refresh_tokens("old_refresh_token", self.request)

        self.assertEqual(resultado["access_token"], "new_access_token")
        self.assertEqual(resultado["refresh_token"], "new_refresh_token")
        mock_rotate.assert_called_once()

    @patch("apps.authentication.services.authentication_service.rotate_refresh_token")
    def test_refresh_tokens_fallo(self, mock_rotate):
        """
        Verifica que refresh_tokens levanta ValueError si token es inválido.
        """
        mock_rotate.side_effect = ValueError("Invalid refresh token")

        with self.assertRaises(ValueError) as context:
            AuthenticationService.refresh_tokens("invalid_token", self.request)

        self.assertIn("Invalid refresh token", str(context.exception))

    @patch("apps.authentication.services.authentication_service.RefreshToken")
    def test_logout_revoca_token(self, mock_refresh_token_model):
        """
        Verifica que logout revoca el refresh token.
        """
        mock_token_obj = MagicMock()
        mock_refresh_token_model.objects.get.return_value = mock_token_obj

        resultado = AuthenticationService.logout("refresh_token_123")

        self.assertEqual(resultado["detail"], "Logout successful")
        mock_token_obj.revoke.assert_called_once()

    @patch("apps.authentication.services.authentication_service.RefreshToken")
    def test_logout_sin_token(self, mock_refresh_token_model):
        """
        Verifica que logout maneja correctamente ausencia de token.
        """
        resultado = AuthenticationService.logout(None)

        self.assertEqual(resultado["detail"], "Logout successful")
        # No debe intentar buscar el token si es None
        mock_refresh_token_model.objects.get.assert_not_called()

    @patch("apps.authentication.services.authentication_service.connections")
    def test_health_check_todos_conectados(self, mock_connections):
        """
        Verifica que health_check retorna como healthy cuando BDs están conectadas.
        """
        # Mock successful connections
        for db in ['default', 'azul']:
            mock_connections[db].ensure_connection.return_value = None

        resultado = AuthenticationService.health_check()

        self.assertEqual(resultado["status"], "healthy")
        self.assertEqual(resultado["databases"]["default"], "connected")
        self.assertEqual(resultado["databases"]["azul"], "connected")

    def test_health_check_bd_desconectada(self):
        """
        Verifica que health_check retorna unhealthy si alguna BD falla,
        sin afectar el estado de la que sí está conectada.

        Nota: se usa un dict real de mocks y no `mock_connections['azul']`,
        porque en un MagicMock todas las claves devuelven el mismo hijo
        (`m['default'] is m['azul']` es True) y ambas BDs quedarían con el
        mismo comportamiento.
        """
        default_conn = MagicMock()
        azul_conn = MagicMock()
        azul_conn.ensure_connection.side_effect = Exception("Connection refused")

        fake_connections = {"default": default_conn, "azul": azul_conn}
        with patch(
            "apps.authentication.services.authentication_service.connections",
            fake_connections,
        ):
            resultado = AuthenticationService.health_check()

        self.assertEqual(resultado["status"], "unhealthy")
        self.assertIn("error", resultado["databases"]["azul"])
        self.assertEqual(resultado["databases"]["default"], "connected")
        default_conn.ensure_connection.assert_called_once()
        azul_conn.ensure_connection.assert_called_once()

    def test_get_secure_cookie_settings(self):
        """
        Verifica que get_secure_cookie_settings retorna config correcta.
        """
        with patch("apps.authentication.services.authentication_service.settings") as mock_settings:
            mock_settings.DEBUG = True
            mock_settings.SECURE_COOKIE = False

            settings = AuthenticationService.get_secure_cookie_settings()

            self.assertTrue(settings["httponly"])
            self.assertEqual(settings["samesite"], "Lax")
            self.assertIn("secure", settings)

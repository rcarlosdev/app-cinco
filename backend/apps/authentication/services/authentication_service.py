import logging
from django.contrib.auth import authenticate
from django.db import connections
from django.conf import settings

from apps.authentication.models import RefreshToken
from .jwt_service import generate_access_token
from .token_service import rotate_refresh_token
from .fingerprint_service import get_device_fingerprint

# Logger de seguridad
security_logger = logging.getLogger('security')


class AuthenticationService:
    """
    Servicio de autenticación.
    Encapsula lógica de login, refresh token, logout y health checks.
    """

    @staticmethod
    def login(username, password, request):
        """
        Autentica usuario y genera tokens JWT.
        
        Args:
            username: Nombre de usuario
            password: Contraseña
            request: HttpRequest (para extraer IP y fingerprint)
            
        Returns:
            dict: {
                'user': {...},
                'access_token': str,
                'refresh_token': str,
            }
            
        Raises:
            ValueError: Si credenciales son inválidas o faltan
        """
        if not username or not password:
            security_logger.warning(
                f"Login attempt with missing credentials from IP: {request.META.get('REMOTE_ADDR')}"
            )
            raise ValueError("Usuario y contraseña requeridos")

        user = authenticate(username=username, password=password)

        if not user:
            security_logger.warning(
                f"Failed login attempt for username: {username} from IP: {request.META.get('REMOTE_ADDR')}"
            )
            raise ValueError("Credenciales inválidas")

        result = AuthenticationService.issue_tokens_for_user(user, request)

        security_logger.info(
            f"Successful login for user: {username} (ID: {user.id}) from IP: {request.META.get('REMOTE_ADDR')}"
        )

        return result

    @staticmethod
    def issue_tokens_for_user(user, request):
        """
        Emite access y refresh token para un usuario ya validado.
        """
        fingerprint = get_device_fingerprint(request)
        access_token = generate_access_token(user, fingerprint)
        refresh_token_obj = AuthenticationService._create_refresh_token(user)
        refresh_token = refresh_token_obj.token

        return {
            "user": AuthenticationService.serialize_user(user),
            "access_token": access_token,
            "refresh_token": refresh_token,
        }

    @staticmethod
    def serialize_user(user):
        """
        Serializa datos públicos del usuario autenticado.
        """
        area = ""
        carpeta = ""
        try:
            from django.db.models import Q
            from apps.empleados.models import Empleado
            empleado = Empleado.objects.filter(
                Q(cedula=user.username) | Q(id=user.id)
            ).first()
            if empleado:
                area = empleado.area or ""
                carpeta = empleado.carpeta or ""
        except Exception:
            pass

        return {
            "id": user.id,
            "username": user.username,
            "nombre": user.first_name,
            "apellido": user.last_name,
            "email": user.email,
            "is_superuser": user.is_superuser,
            "area": area,
            "carpeta": carpeta,
        }

    @staticmethod
    def refresh_tokens(refresh_token_str, request):
        """
        Rota refresh token y genera nuevo access token.
        
        Args:
            refresh_token_str: Token de refresh a rotar
            request: HttpRequest (para extraer fingerprint)
            
        Returns:
            dict: {
                'access_token': str,
                'refresh_token': str,
            }
            
        Raises:
            ValueError: Si token es inválido, expirado, revocado o hay reuso
        """
        if not refresh_token_str:
            security_logger.warning(
                f"Refresh attempt without token from IP: {request.META.get('REMOTE_ADDR')}"
            )
            raise ValueError("refresh_token es requerido")

        # Generar fingerprint del dispositivo
        fingerprint = get_device_fingerprint(request)

        try:
            tokens = rotate_refresh_token(refresh_token_str, fingerprint)
            security_logger.info(
                f"Token refresh successful from IP: {request.META.get('REMOTE_ADDR')}"
            )
        except ValueError as e:
            error_msg = str(e)
            security_logger.error(
                f"Token refresh failed: {error_msg} from IP: {request.META.get('REMOTE_ADDR')}"
            )
            raise

        return tokens

    @staticmethod
    def logout(refresh_token_str):
        """
        Revoca refresh token del usuario (logout).
        
        Args:
            refresh_token_str: Token de refresh a revocar (puede ser None)
            
        Returns:
            dict: {'detail': 'Logout successful'}
        """
        if refresh_token_str:
            try:
                token_obj = RefreshToken.objects.get(token=refresh_token_str)
                token_obj.revoke()
                security_logger.info(
                    f"User logged out successfully (User ID: {token_obj.user.id})"
                )
            except RefreshToken.DoesNotExist:
                security_logger.warning(
                    "Logout attempt with invalid token"
                )
                pass  # Token ya no existe o es inválido
        else:
            security_logger.warning("Logout attempt without token")

        return {"detail": "Logout successful"}

    @staticmethod
    def health_check():
        """
        Verifica estado del sistema (conexiones a BDs).
        
        Returns:
            dict: {
                'status': 'healthy|unhealthy',
                'service': str,
                'databases': {...},
                'error': str (solo si status=unhealthy)
            }
        """
        try:
            # Verificar conexión a base de datos default
            connections['default'].ensure_connection()
            db_default_status = "connected"
        except Exception as e:
            db_default_status = f"error: {str(e)}"

        try:
            # Verificar conexión a base de datos azul
            connections['azul'].ensure_connection()
            db_azul_status = "connected"
        except Exception as e:
            db_azul_status = f"error: {str(e)}"

        databases = {
            "default": db_default_status,
            "azul": db_azul_status
        }

        # Si alguna BD falló
        if "error" in db_default_status or "error" in db_azul_status:
            return {
                "status": "unhealthy",
                "service": "app-cinco-backend",
                "databases": databases,
            }

        return {
            "status": "healthy",
            "service": "app-cinco-backend",
            "databases": databases,
        }

    @staticmethod
    def _create_refresh_token(user):
        """
        Crea nuevo RefreshToken para usuario.
        Método privado auxiliar.
        """
        from datetime import timedelta
        from django.utils import timezone

        refresh_token = RefreshToken.objects.create(
            user=user,
            token=RefreshToken.generate(),
            expires_at=timezone.now() + timedelta(days=7)
        )
        return refresh_token

    @staticmethod
    def get_secure_cookie_settings():
        """
        Retorna settings para cookies httpOnly.
        Útil para views que establecen cookies.
        """
        secure_cookie = getattr(settings, 'SECURE_COOKIE', not settings.DEBUG)
        return {
            "httponly": True,
            "secure": secure_cookie,
            "samesite": "Strict",
        }

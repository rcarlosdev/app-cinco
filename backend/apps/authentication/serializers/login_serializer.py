from django.contrib.auth import authenticate
from rest_framework import serializers


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        user = authenticate(
            username=data["username"],
            password=data["password"]
        )

        if not user:
            raise serializers.ValidationError("Credenciales inválidas")

        if not user.is_active:
            raise serializers.ValidationError("Usuario inactivo")

        data["user"] = user
        return data
    
class LoginRequestSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()


class AuthUserSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    nombre = serializers.CharField(allow_blank=True)
    apellido = serializers.CharField(allow_blank=True)
    email = serializers.EmailField(allow_blank=True)
    is_superuser = serializers.BooleanField()
    area = serializers.CharField(allow_blank=True, required=False)
    carpeta = serializers.CharField(allow_blank=True, required=False)


class LoginResponseSerializer(serializers.Serializer):
    user = AuthUserSerializer()


class SessionResponseSerializer(serializers.Serializer):
    authenticated = serializers.BooleanField()
    user = AuthUserSerializer()


class LegacyLoginResponseSerializer(serializers.Serializer):
    access_token = serializers.CharField()
    refresh_token = serializers.CharField()
    user = serializers.DictField()
    api_client = serializers.DictField()


class LegacyExchangeRequestSerializer(serializers.Serializer):
    legacy_token = serializers.CharField()


from .settings import *

# Sobrescribir DATABASES para usar SQLite en memoria en las pruebas
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    },
    'azul': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    },
    'logistica_cinco': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

# Deshabilitar el router de base de datos para que todas las pruebas usen la base de datos sqlite3 por defecto
DATABASE_ROUTERS = []

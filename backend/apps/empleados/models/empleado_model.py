from django.db import models

class Empleado(models.Model):
    ESTADO_CHOICES = [
        ('ACTIVO', 'Activo'),
        ('INACTIVO', 'Inactivo'),
        ('SUSPENDIDO', 'Suspendido'),
    ]
    
    SEDE_CHOICES = [
        ('BOGOTA', 'Bogot├í'),
        ('CALI', 'Cali'),
        ('CAUCASIA', 'Caucasia'),
        ('MEDELLIN', 'Medell├¡n'),
        ('MONTERIA', 'Monter├¡a'),
        ('ORIENTE', 'Oriente'),
        ('SINCELEJO', 'Sincelejo'),
        ('TARAZA', 'Taraz├í'),
        ('YARUMAL', 'Yarumal'),
    ]
    
    id = models.AutoField(primary_key=True)
    cedula = models.CharField(max_length=50, unique=True)
    codigo_sap = models.CharField(max_length=50, unique=True)
    permiso = models.CharField(max_length=100, blank=True, null=True)
    pasaporte = models.CharField(max_length=50, blank=True, null=True)
    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    zona_nodo = models.CharField(max_length=100, blank=True, null=True)
    area = models.CharField(max_length=100, blank=True, null=True)
    carpeta = models.CharField(max_length=100, blank=True, null=True)
    sede = models.CharField(max_length=100, blank=True, null=False, choices=SEDE_CHOICES, default='MEDELLIN')
    movil = models.CharField(max_length=100, blank=True, null=True)
    cargo = models.CharField(max_length=100, blank=True, null=True)
    funcion_cargo = models.CharField(max_length=255, blank=True, null=True)
    tipo_labor = models.CharField(max_length=100, blank=True, null=True)
    puesto = models.CharField(max_length=100, blank=True, null=True)
    nivelestudio = models.CharField(max_length=100, blank=True, null=True)
    # supervisor -> relacionar con otro empleado (cedula en el modelo actual)
    supervisor = models.CharField(max_length=100, blank=True, null=True)
    estado = models.CharField(max_length=50, choices=ESTADO_CHOICES, blank=True, null=False, default='ACTIVO')
    correo = models.EmailField(max_length=255, blank=True, null=True)
    placa = models.CharField(max_length=50, blank=True, null=True)
    leer = models.TextField(blank=True, null=True)
    insertar = models.TextField(blank=True, null=True)
    editar = models.TextField(blank=True, null=True)
    importar = models.TextField(blank=True, null=True)
    manual = models.TextField(blank=True, null=True)
    admin = models.TextField(blank=True, null=True)
    exportar = models.TextField(blank=True, null=True)
    password = models.CharField(max_length=255)
    codigo_encri = models.CharField(max_length=255, blank=True, null=True)
    edit = models.CharField(max_length=100, blank=True, null=True)
    fecha_edit = models.DateTimeField(blank=True, null=True)
    # cer_alturas = models.CharField(max_length=100, blank=True, null=True)
    # cer_tecnico = models.CharField(max_length=100, blank=True, null=True)
    fnacimiento = models.DateField(blank=True, null=True)
    fecha_ingreso = models.DateField(blank=True, null=True)
    fexpedicion = models.DateField(blank=True, null=True)
    fecha_egreso = models.DateField(blank=True, null=True)
    # calturas = models.CharField(max_length=100, blank=True, null=True)
    # ctecnico = models.CharField(max_length=100, blank=True, null=True)
    solicitud = models.CharField(max_length=100, blank=True, null=True)
    chat = models.CharField(max_length=100, blank=True, null=True)
    img = models.CharField(max_length=255, blank=True, null=True)
    permiso_trabajo = models.CharField(max_length=100, blank=True, null=True)
    celular_personal = models.CharField(max_length=50, blank=True, null=True)
    celular_alterno = models.CharField(max_length=50, blank=True, null=True)
    telefono_fijo = models.CharField(max_length=50, blank=True, null=True)
    direccion_residencia_actual = models.CharField(max_length=255, blank=True, null=True)
    correo_electronico_personal = models.EmailField(max_length=255, blank=True, null=True)
    link_foto = models.CharField(max_length=255, blank=True, null=True)
    carnet = models.CharField(max_length=100, blank=True, null=True)
    dotacion = models.CharField(max_length=100, blank=True, null=True)
    fecha_carnet = models.DateField(blank=True, null=True)
    genero = models.CharField(max_length=50, blank=True, null=True)
    eps = models.CharField(max_length=100, blank=True, null=True)
    arl = models.CharField(max_length=100, blank=True, null=True)
    certificado_arl = models.CharField(max_length=100, blank=True, null=True)
    afp = models.CharField(max_length=100, blank=True, null=True)
    vacunacion = models.CharField(max_length=100, blank=True, null=True)
    # datos -> informaci├│n adicional en formato JSON
    datos = models.JSONField(blank=True, null=True)
    email_personal = models.EmailField(max_length=255, blank=True, null=True)
    email_verificar = models.CharField(max_length=100, blank=True, null=True)
    grupo_comiciones = models.CharField(max_length=100, blank=True, null=True)
    
    class Meta:
        managed = False  # ­ƒö┤ CR├ìTICO
        db_table = "cinco_base_de_personal"
        app_label = "empleados"


class EmpleadoSiigo(models.Model):
    id = models.AutoField(primary_key=True)
    cedula = models.CharField(max_length=20)
    estado = models.CharField(max_length=20)
    centro_costo = models.CharField(max_length=20)
    salario = models.CharField(max_length=20)
    datos = models.JSONField(blank=True, null=True)
    edit = models.CharField(max_length=20)
    fecha_edit = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "cinco_base_de_personal_siigo"
        app_label = "empleados"

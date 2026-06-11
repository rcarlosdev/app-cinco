# Guia Paso A Paso: Consumir Certificado Laboral PDF

## Objetivo

Esta guia explica como consumir el endpoint que genera el certificado laboral en PDF desde:

- JavaScript
- PHP
- una app web existente

El endpoint ya genera el archivo PDF en backend y responde como descarga binaria.

## Endpoint

Ruta:

```text
GET /empleados/empleados/{id}/certificado-laboral/
```

Parametro opcional:

```text
document_type=CC|PT|TI|CE
```

Ejemplo:

```text
http://localhost:8000/empleados/empleados/5/certificado-laboral/?document_type=CC
```

## Que devuelve

La respuesta del backend incluye:

- `Content-Type: application/pdf`
- `Content-Disposition: attachment; filename="certificado_laboral_5.pdf"`

Eso significa que debe consumirse como archivo binario, no como JSON ni como texto.

## Paso 1: confirmar autenticacion

Antes de probar desde frontend o PHP, valida como se autentica tu app:

- Si la app usa login web con cookies y sesion: usa credenciales/cookies.
- Si la app usa JWT: envia `Authorization: Bearer TU_TOKEN`.
- Si la app usa integracion externa: envia `X-API-Key: TU_API_KEY`.

## Paso 2: probar primero en navegador

Si ya tienes sesion iniciada en el sistema, abre una URL como esta:

```text
http://localhost:8000/empleados/empleados/5/certificado-laboral/
```

Si todo esta bien, el navegador descargara el PDF.

## Paso 3: consumir desde JavaScript con fetch

Este ejemplo sirve para frontend web:

```ts
async function descargarCertificado(id, documentType = "CC") {
  const url = `http://localhost:8000/empleados/empleados/${id}/certificado-laboral/?document_type=${documentType}`;

  const response = await fetch(url, {
    method: "GET",
    credentials: "include",
    headers: {
      // "Authorization": "Bearer TU_TOKEN",
      // "X-API-Key": "TU_API_KEY",
    },
  });

  if (!response.ok) {
    throw new Error(`Error al descargar certificado: ${response.status}`);
  }

  const blob = await response.blob();
  const downloadUrl = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = downloadUrl;
  anchor.download = `certificado_${id}.pdf`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.URL.revokeObjectURL(downloadUrl);
}
```

Uso:

```ts
await descargarCertificado(5, "CC");
```

## Paso 4: consumir desde JavaScript con axios

Si tu proyecto ya usa `axios`, debes pedir la respuesta como `blob`:

```ts
import axios from "axios";

async function descargarCertificado(id, documentType = "CC") {
  const response = await axios.get(
    `http://localhost:8000/empleados/empleados/${id}/certificado-laboral/`,
    {
      params: { document_type: documentType },
      responseType: "blob",
      withCredentials: true,
      headers: {
        // Authorization: "Bearer TU_TOKEN",
        // "X-API-Key": "TU_API_KEY",
      },
    }
  );

  const url = window.URL.createObjectURL(response.data);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `certificado_${id}.pdf`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.URL.revokeObjectURL(url);
}
```

## Paso 5: implementar esto en el frontend del proyecto actual

En este proyecto ya existe un servicio de empleados en:

```text
frontend/src/services/empleado.service.ts
```

Puedes agregar esta funcion:

```ts
export const downloadCertificadoLaboral = async (
  id: number,
  documentType?: "CC" | "PT" | "TI" | "CE",
): Promise<Blob> => {
  const response = await api.get(`/empleados/empleados/${id}/certificado-laboral/`, {
    params: documentType ? { document_type: documentType } : undefined,
    responseType: "blob",
  });

  return response.data as Blob;
};
```

Luego, desde un boton:

```ts
const handleDownloadCertificado = async () => {
  const blob = await downloadCertificadoLaboral(5, "CC");
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "certificado_laboral.pdf";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.URL.revokeObjectURL(url);
};
```

Ejemplo en React:

```tsx
<button onClick={() => void handleDownloadCertificado()}>
  Descargar certificado
</button>
```

## Paso 6: consumir desde PHP con cURL

Este ejemplo descarga el PDF desde backend y lo entrega al navegador:

```php
<?php
$id = 5;
$documentType = "CC";
$url = "http://localhost:8000/empleados/empleados/{$id}/certificado-laboral/?document_type={$documentType}";

$ch = curl_init($url);
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
curl_setopt($ch, CURLOPT_HTTPHEADER, [
    // "Authorization: Bearer TU_TOKEN",
    // "X-API-Key: TU_API_KEY",
]);
curl_setopt($ch, CURLOPT_COOKIEFILE, "");

$pdf = curl_exec($ch);
$httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
curl_close($ch);

if ($httpCode !== 200) {
    http_response_code($httpCode);
    echo "No fue posible generar el certificado";
    exit;
}

header("Content-Type: application/pdf");
header("Content-Disposition: attachment; filename=certificado_{$id}.pdf");
echo $pdf;
```

## Paso 7: guardar el PDF en disco desde PHP

Si no quieres descargarlo al navegador sino guardarlo:

```php
<?php
file_put_contents(__DIR__ . "/certificado_5.pdf", $pdf);
```

## Paso 8: usarlo desde una app PHP con enlace

Puedes crear un archivo como `descargar_certificado.php` y llamarlo desde un link:

```html
<a href="descargar_certificado.php?id=5&document_type=CC">
  Descargar certificado
</a>
```

Y dentro de `descargar_certificado.php`:

```php
<?php
$id = $_GET["id"] ?? "";
$documentType = $_GET["document_type"] ?? "CC";
```

Despues reutilizas el bloque `cURL` del paso anterior.

## Paso 9: errores comunes

### El navegador descarga un archivo vacio

Revisa:

- que el `id` del empleado exista
- que el usuario tenga autenticacion valida
- que no estes leyendo la respuesta como JSON

### Swagger muestra texto raro del PDF

Eso es normal si Swagger intenta renderizar binarios como texto. Para uso real debes:

- descargarlo desde frontend como `blob`
- o consumirlo desde PHP como binario

### El frontend falla con CORS o sesion

Revisa:

- `withCredentials: true` en `axios`
- `credentials: "include"` en `fetch`
- que el backend permita el origen frontend
- que la sesion siga activa

### El backend responde 401 o 403

Revisa:

- JWT vencido
- API key invalida
- sesion no iniciada

## Paso 10: forma recomendada segun el tipo de app

- App frontend React/Next/Vue: usar `axios` o `fetch` con `blob`
- App PHP legacy: usar `cURL` y reenviar el PDF al navegador
- Integracion servidor a servidor: usar `cURL` o cliente HTTP y guardar el binario

## Resumen rapido

1. Llama `GET /empleados/empleados/{id}/certificado-laboral/`
2. Envia autenticacion si aplica
3. Trata la respuesta como binario
4. En JavaScript usa `blob`
5. En PHP usa `cURL`
6. Descarga o guarda el archivo `.pdf`

## Ejemplo final de prueba rapida

### JavaScript

```ts
await descargarCertificado(5, "CC");
```

### PHP

```php
<?php
require "descargar_certificado.php";
```

import logging
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import msal
import requests
from django.conf import settings
from django.utils import timezone

from apps.implementacion_fo.models import MappingPredio, SharePointMappingConfig

logger = logging.getLogger(__name__)


class SharePointMappingService:
    """
    Servicio de integración entre el módulo de Mapping de Implementación FO
    y Microsoft SharePoint mediante Microsoft Graph API.

    Gestiona:
    - Autenticación segura con token de Azure (MSAL).
    - Mapeo dinámico de filas por barrio hacia archivos Excel (.xlsx) o Listas.
    - Reintentos con retroceso exponencial ante bloqueos (423/409) o cuotas (429).
    - Inserción individual o en lote (batch) para alta concurrencia.
    """

    GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
    _msal_app: Optional[msal.ConfidentialClientApplication] = None
    _list_columns_cache: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def get_msal_client(cls) -> msal.ConfidentialClientApplication:
        """Obtiene o inicializa el cliente MSAL con caché interna de tokens."""
        if cls._msal_app is None:
            tenant_id = getattr(settings, "SHAREPOINT_TENANT_ID", "") or ""
            client_id = getattr(settings, "SHAREPOINT_CLIENT_ID", "") or ""
            client_secret = getattr(settings, "SHAREPOINT_CLIENT_SECRET", "") or ""

            if not (tenant_id and client_id and client_secret):
                raise ValueError(
                    "Faltan credenciales de Microsoft Graph en settings / .env: "
                    "SHAREPOINT_TENANT_ID, SHAREPOINT_CLIENT_ID, SHAREPOINT_CLIENT_SECRET"
                )

            authority = f"https://login.microsoftonline.com/{tenant_id}"
            cls._msal_app = msal.ConfidentialClientApplication(
                client_id=client_id,
                client_credential=client_secret,
                authority=authority,
            )
        return cls._msal_app

    @classmethod
    def get_access_token(cls) -> str:
        """
        Adquiere un token de acceso para Microsoft Graph API.
        MSAL busca automáticamente en su caché en memoria y renueva el token cuando expira.
        """
        app = cls.get_msal_client()
        scopes = ["https://graph.microsoft.com/.default"]
        result = app.acquire_token_silent(scopes=scopes, account=None)

        if not result:
            logger.info("Adquiriendo nuevo token de Microsoft Graph con credenciales de cliente...")
            result = app.acquire_token_for_client(scopes=scopes)

        if "access_token" in result:
            return result["access_token"]

        error_desc = result.get("error_description", result.get("error", "Error desconocido al obtener token"))
        logger.error(f"Error al autenticar con Microsoft Graph: {error_desc}")
        raise RuntimeError(f"Error al autenticar con Microsoft Graph: {error_desc}")

    @classmethod
    def _headers(cls) -> Dict[str, str]:
        token = cls.get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    @classmethod
    @classmethod
    def resolve_site_info(cls, site_url: Optional[str] = None) -> Dict[str, Any]:
        """
        Dada una URL de SharePoint (incluso si incluye carpetas o parámetros de vista),
        resuelve el ID único del sitio (Site ID) y la ruta relativa.
        Ejemplos soportados:
        - https://empresa.sharepoint.com/sites/MiSitio
        - https://empresa.sharepoint.com/sites/MiSitio/Documentos Compartidos/CarpetaMapping
        """
        url = site_url or getattr(settings, "SHAREPOINT_SITE_URL", "")
        if not url:
            raise ValueError("No se configuró SHAREPOINT_SITE_URL en las variables de entorno.")

        parsed = urlparse(url)
        hostname = parsed.netloc

        # Extraer solo la parte del sitio /sites/<nombre> o /teams/<nombre>
        path_segments = [seg for seg in parsed.path.strip("/").split("/") if seg]
        if len(path_segments) >= 2 and path_segments[0].lower() in ("sites", "teams"):
            site_relative_path = f"/{path_segments[0]}/{path_segments[1]}"
        else:
            site_relative_path = parsed.path.rstrip("/")

        endpoint = f"{cls.GRAPH_BASE_URL}/sites/{hostname}:{site_relative_path}"
        response = requests.get(endpoint, headers=cls._headers(), timeout=15)
        response.raise_for_status()
        data = response.json()
        return {
            "site_id": data["id"],
            "site_name": data.get("displayName") or data.get("name"),
            "hostname": hostname,
            "site_relative_path": site_relative_path,
        }

    @classmethod
    def resolve_site_id(cls, site_url: Optional[str] = None) -> str:
        """Retorna únicamente el Site ID."""
        info = cls.resolve_site_info(site_url)
        return info["site_id"]

    @classmethod
    def list_drives(cls, site_id: str) -> List[Dict[str, Any]]:
        """Lista las bibliotecas de documentos (Drives) dentro de un sitio."""
        endpoint = f"{cls.GRAPH_BASE_URL}/sites/{site_id}/drives"
        response = requests.get(endpoint, headers=cls._headers(), timeout=15)
        response.raise_for_status()
        return response.json().get("value", [])

    @classmethod
    def list_excel_files(cls, drive_id: str, folder_item_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Lista todos los archivos de Excel (.xlsx) dentro de un Drive o carpeta.
        Usa búsqueda recursiva para encontrar archivos tanto en la raíz como en subcarpetas.
        """
        if folder_item_id:
            endpoint = f"{cls.GRAPH_BASE_URL}/drives/{drive_id}/items/{folder_item_id}/children"
        else:
            # Buscar recursivamente todos los .xlsx en el drive
            endpoint = f"{cls.GRAPH_BASE_URL}/drives/{drive_id}/root/search(q='.xlsx')"

        try:
            response = requests.get(endpoint, headers=cls._headers(), timeout=15)
            response.raise_for_status()
            items = response.json().get("value", [])
        except Exception:
            # Fallback a root/children directo si search no estuviera disponible
            fallback_endpoint = f"{cls.GRAPH_BASE_URL}/drives/{drive_id}/root/children"
            response = requests.get(fallback_endpoint, headers=cls._headers(), timeout=15)
            response.raise_for_status()
            items = response.json().get("value", [])

        excel_files = []
        for item in items:
            name = item.get("name", "")
            if name.lower().endswith(".xlsx") and not name.startswith("~$"):
                # Sugerir barrio limpiando prefijos/sufijos
                base_name = name.rsplit(".", 1)[0]
                barrio_sug = base_name.replace("Mapping_", "").replace("MAPPING_", "").replace("Predios_", "").replace("_", " ").strip().upper()
                excel_files.append({
                    "id": item.get("id"),
                    "name": name,
                    "barrio_sugerido": barrio_sug,
                    "web_url": item.get("webUrl"),
                    "drive_id": drive_id,
                })
        return excel_files

    @classmethod
    def auto_descubrir_barrios(cls, drive_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Descubre automáticamente los archivos .xlsx de la carpeta de SharePoint
        y sincroniza o crea las configuraciones por barrio en la base de datos.
        """
        site_id = cls.resolve_site_id()
        drives = cls.list_drives(site_id)
        if not drives:
            return {"success": False, "error": "No se encontraron bibliotecas de documentos (Drives) en el sitio."}

        target_drive_id = drive_id or drives[0]["id"]
        archivos = cls.list_excel_files(target_drive_id)

        creados = 0
        actualizados = 0

        for arch in archivos:
            barrio = arch["barrio_sugerido"]
            item_id = arch["id"]
            if not barrio or not item_id:
                continue

            config, created = SharePointMappingConfig.objects.get_or_create(
                barrio=barrio,
                defaults={
                    "descripcion": f"Auto-descubierto desde {arch['name']}",
                    "tipo_destino": "EXCEL",
                    "sp_drive_id": target_drive_id,
                    "sp_item_id": item_id,
                    "sp_table_name": "Tabla1",
                    "activo": True,
                },
            )
            if created:
                creados += 1
            else:
                config.sp_drive_id = target_drive_id
                config.sp_item_id = item_id
                config.activo = True
                config.save(update_fields=["sp_drive_id", "sp_item_id", "activo"])
                actualizados += 1

        return {
            "success": True,
            "total_archivos_encontrados": len(archivos),
            "creados": creados,
            "actualizados": actualizados,
            "archivos": archivos,
        }

    # =========================================================================
    # SECCIÓN: LISTAS DE SHAREPOINT (MICROSOFT LISTS)
    # =========================================================================

    @classmethod
    def list_sharepoint_lists(cls, site_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Lista las listas personalizadas de SharePoint en el sitio (excluye listas del sistema y bibliotecas).
        """
        sid = site_id or cls.resolve_site_id()
        endpoint = f"{cls.GRAPH_BASE_URL}/sites/{sid}/lists"
        response = requests.get(endpoint, headers=cls._headers(), timeout=15)
        response.raise_for_status()
        raw_lists = response.json().get("value", [])

        excluded_names = {
            "wte",
            "appdata",
            "sharinglinks",
            "taxonomyhiddenlist",
            "access requests",
            "app packages",
        }
        custom_lists = []
        for l in raw_lists:
            name = l.get("name", "")
            d_name = l.get("displayName", "")
            is_hidden = l.get("list", {}).get("hidden", False)
            template = l.get("list", {}).get("template", "")

            if name.lower() in excluded_names or is_hidden or template == "documentLibrary":
                continue

            # Extraer el nombre del barrio limpiando prefijos (mapping_, mapping-, mapping , predios_, etc.)
            limpio = re.sub(r"^(mapping|predios)[_\s\-]+", "", d_name, flags=re.IGNORECASE)
            barrio_sug = limpio.replace("_", " ").strip().upper()

            custom_lists.append({
                "id": l.get("id"),
                "name": name,
                "displayName": d_name,
                "barrio_sugerido": barrio_sug,
                "web_url": l.get("webUrl"),
                "description": l.get("description", ""),
            })

        return custom_lists

    @classmethod
    def auto_descubrir_listas(cls, site_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Descubre las listas creadas en el sitio de SharePoint y registra o actualiza
        sus configuraciones por barrio en la base de datos.
        - Si una lista cambia de nombre en SharePoint, actualiza el barrio en la base de datos.
        - Si una lista es eliminada de SharePoint, desactiva la configuración para no mostrarla en el selector.
        """
        sid = site_id or cls.resolve_site_id()
        listas = cls.list_sharepoint_lists(sid)
        creadas = 0
        actualizadas = 0
        list_ids_encontrados = set()

        for l in listas:
            barrio = l["barrio_sugerido"]
            list_id = l["id"]
            if not barrio or not list_id:
                continue

            list_ids_encontrados.add(list_id)

            # 1. Buscar si ya existe por el ID único e inmutable de la lista en SharePoint
            config = SharePointMappingConfig.objects.filter(
                sp_list_id=list_id, tipo_destino="LISTA"
            ).first()

            if config:
                # La lista ya existía: si le cambiaron el nombre en SharePoint, actualizamos el barrio
                if config.barrio != barrio:
                    # Limpiar cualquier colisión previa con el nuevo nombre
                    SharePointMappingConfig.objects.filter(barrio=barrio).exclude(id=config.id).delete()
                    config.barrio = barrio
                config.descripcion = f"Lista SharePoint: {l['displayName']}"
                config.activo = True
                config.save()
                actualizadas += 1
            else:
                # 2. No existía por ID: crear o actualizar por nombre de barrio
                config, created = SharePointMappingConfig.objects.update_or_create(
                    barrio=barrio,
                    defaults={
                        "descripcion": f"Lista SharePoint: {l['displayName']}",
                        "tipo_destino": "LISTA",
                        "sp_list_id": list_id,
                        "activo": True,
                    },
                )
                if created:
                    creadas += 1
                else:
                    actualizadas += 1

        # 3. Si alguna lista ya no existe en SharePoint, desactivarla en la base de datos
        if list_ids_encontrados:
            SharePointMappingConfig.objects.filter(
                tipo_destino="LISTA"
            ).exclude(sp_list_id__in=list_ids_encontrados).update(activo=False)

        return {
            "success": True,
            "total_listas_encontradas": len(listas),
            "creadas": creadas,
            "actualizadas": actualizadas,
            "listas": listas,
        }

    @classmethod
    def get_list_columns(cls, list_id: str, site_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Obtiene el mapeo de nombres de columnas visibles en la lista de SharePoint
        hacia sus nombres internos (ej: 'NOMBRE CONJUNTO' -> ('field_1', False)) y si es numérica.
        """
        if list_id in cls._list_columns_cache:
            return cls._list_columns_cache[list_id]

        sid = site_id or cls.resolve_site_id()
        endpoint = f"{cls.GRAPH_BASE_URL}/sites/{sid}/lists/{list_id}/columns"
        response = requests.get(endpoint, headers=cls._headers(), timeout=15)
        response.raise_for_status()
        raw_cols = response.json().get("value", [])

        col_map = {}
        for c in raw_cols:
            display_name = (c.get("displayName") or "").strip().upper()
            internal_name = c.get("name")
            is_number = "number" in c
            if display_name and internal_name:
                col_map[display_name] = (internal_name, is_number)

        # En SharePoint Lists, LinkTitle corresponde a la columna principal visual (AMP)
        if "AMP" not in col_map or col_map["AMP"][0] in ("LinkTitle", "LinkTitleNoMenu"):
            col_map["AMP"] = ("Title", False)
        if "TITLE" not in col_map:
            col_map["TITLE"] = ("Title", False)

        cls._list_columns_cache[list_id] = col_map
        return col_map

    @classmethod
    def format_predio_for_list(
        cls,
        predio: MappingPredio,
        col_map: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Convierte una instancia de MappingPredio en el objeto 'fields' que espera Graph API
        para una fila/elemento en una Lista de SharePoint.
        """
        raw_values = {
            "AMP": predio.lote_amp or "",
            "NOMBRE CONJUNTO": predio.nombre_conjunto or "",
            "NOMBRECALL": predio.nombre_calle or "",
            "PLACAUNIDA": predio.placa_unidad or "",
            "NUM_CASAS": predio.num_casas or 0,
            "APTOS": predio.num_apartamentos or 0,
            "LOCALES": predio.num_locales or 0,
            "PISOS": predio.num_pisos or 1,
            "BARRIO": predio.barrio or "",
            "INT": predio.interior or "",
            "DISTRIBUCION": predio.distribucion or "",
            "CORDX": float(predio.latitud) if predio.latitud is not None else None,
            "CORDY": float(predio.longitud) if predio.longitud is not None else None,
            "NOMBRECALLANT2": predio.calle_alterna_2 or "",
            "PLACAUNIDAANT2": predio.placa_alterna_2 or "",
            "NOMBRECALLANT3": predio.calle_alterna_3 or "",
            "PLACAUNIDAANT3": predio.placa_alterna_3 or "",
        }

        fields_payload = {}
        for std_name, value in raw_values.items():
            if std_name in col_map:
                internal_name, is_number = col_map[std_name]
                if is_number:
                    if value is None or value == "":
                        continue
                    try:
                        fields_payload[internal_name] = float(value)
                    except (ValueError, TypeError):
                        pass
                else:
                    fields_payload[internal_name] = str(value) if value is not None else ""

        if "Title" not in fields_payload:
            fields_payload["Title"] = str(predio.lote_amp or predio.id)

        return fields_payload

    @classmethod
    def append_item_to_list(
        cls,
        list_id: str,
        fields_payload: Dict[str, Any],
        site_id: Optional[str] = None,
        max_retries: int = 3,
        backoff_seconds: float = 1.0,
    ) -> Dict[str, Any]:
        """
        Inserta un nuevo elemento en una lista de SharePoint via Microsoft Graph API.
        Es atómico y no sufre de bloqueos de archivo como Excel.
        """
        sid = site_id or cls.resolve_site_id()
        endpoint = f"{cls.GRAPH_BASE_URL}/sites/{sid}/lists/{list_id}/items"
        body = {"fields": fields_payload}

        attempt = 0
        last_error = ""

        while attempt < max_retries:
            attempt += 1
            try:
                response = requests.post(
                    endpoint,
                    headers=cls._headers(),
                    json=body,
                    timeout=20,
                )

                if response.status_code in (200, 201):
                    return response.json()

                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 2))
                    logger.warning(f"Límite de tasa Graph API (HTTP 429), esperando {retry_after}s")
                    time.sleep(retry_after)
                    continue

                response.raise_for_status()

            except requests.exceptions.RequestException as exc:
                last_error = str(exc)
                logger.warning(f"Error al insertar en lista SharePoint (intento {attempt}/{max_retries}): {exc}")
                time.sleep(backoff_seconds)
                backoff_seconds *= 2

        raise RuntimeError(f"Fallo al insertar en lista SharePoint tras {max_retries} intentos: {last_error}")

    # =========================================================================
    # SECCIÓN: ARCHIVOS EXCEL (.XLSX)
    # =========================================================================

    @classmethod
    def list_tables(cls, drive_id: str, item_id: str) -> List[Dict[str, Any]]:
        """Lista las tablas de Excel existentes dentro de un archivo .xlsx."""
        endpoint = f"{cls.GRAPH_BASE_URL}/drives/{drive_id}/items/{item_id}/workbook/tables"
        response = requests.get(endpoint, headers=cls._headers(), timeout=15)
        response.raise_for_status()
        return response.json().get("value", [])

    @classmethod
    def get_table_columns(cls, drive_id: str, item_id: str, table_name: str) -> List[str]:
        """Obtiene la lista de nombres de columnas en su orden actual en la tabla de Excel."""
        endpoint = f"{cls.GRAPH_BASE_URL}/drives/{drive_id}/items/{item_id}/workbook/tables/{table_name}/columns"
        response = requests.get(endpoint, headers=cls._headers(), timeout=15)
        response.raise_for_status()
        columns_data = response.json().get("value", [])
        return [col["name"] for col in columns_data]

    @classmethod
    def append_rows_to_excel(
        cls,
        drive_id: str,
        item_id: str,
        table_name: str,
        rows_values: List[List[Any]],
        max_retries: int = 4,
        backoff_seconds: float = 1.5,
    ) -> Dict[str, Any]:
        """
        Inserta una o varias filas en la tabla del archivo Excel en SharePoint.
        Implementa reintentos con backoff exponencial si el archivo está bloqueado (423/409)
        o ante throttling de cuota (429).
        """
        endpoint = f"{cls.GRAPH_BASE_URL}/drives/{drive_id}/items/{item_id}/workbook/tables/{table_name}/rows/add"
        body = {"values": rows_values}

        attempt = 0
        last_error = ""

        while attempt < max_retries:
            attempt += 1
            try:
                response = requests.post(
                    endpoint,
                    headers=cls._headers(),
                    json=body,
                    timeout=30,
                )

                if response.status_code in (200, 201):
                    return response.json()

                if response.status_code in (423, 409):
                    last_error = f"Archivo bloqueado temporalmente (HTTP {response.status_code})"
                    logger.warning(
                        f"SharePoint Excel {item_id} ocupado (intento {attempt}/{max_retries}). "
                        f"Reintentando en {backoff_seconds}s..."
                    )
                    time.sleep(backoff_seconds)
                    backoff_seconds *= 2
                    continue

                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 3))
                    last_error = f"Límite de tasa Graph API (HTTP 429), esperando {retry_after}s"
                    logger.warning(last_error)
                    time.sleep(retry_after)
                    continue

                response.raise_for_status()

            except requests.exceptions.RequestException as exc:
                last_error = str(exc)
                logger.warning(f"Error de red/petición al insertar en Excel (intento {attempt}/{max_retries}): {exc}")
                time.sleep(backoff_seconds)
                backoff_seconds *= 2

        raise RuntimeError(f"Fallo al insertar filas en Excel tras {max_retries} intentos: {last_error}")

    @classmethod
    def format_predio_row(
        cls,
        predio: MappingPredio,
        column_order: Optional[List[str]] = None,
    ) -> List[Any]:
        """
        Convierte una instancia de MappingPredio en un arreglo de valores para fila de Excel.
        Si se pasa column_order, hace coincidir los valores con el orden exacto de los encabezados.
        """
        # Mapeo inverso de encabezados estándar hacia campos del modelo
        header_to_val = {
            "NOMBRE CONJUNTO": predio.nombre_conjunto or "",
            "NOMBRECALL": predio.nombre_calle or "",
            "PLACAUNIDA": predio.placa_unidad or "",
            "NUM_CASAS": predio.num_casas or 0,
            "APTOS": predio.num_apartamentos or 0,
            "LOCALES": predio.num_locales or 0,
            "PISOS": predio.num_pisos or 1,
            "BARRIO": predio.barrio or "",
            "INT": predio.interior or "",
            "NOMBRECALLANT2": predio.calle_alterna_2 or "",
            "PLACAUNIDAANT2": predio.placa_alterna_2 or "",
            "NOMBRECALLANT3": predio.calle_alterna_3 or "",
            "PLACAUNIDAANT3": predio.placa_alterna_3 or "",
            "DISTRIBUCION": predio.distribucion or "",
            "AMP": predio.lote_amp or "",
            "CORDX": float(predio.latitud) if predio.latitud is not None else "",
            "CORDY": float(predio.longitud) if predio.longitud is not None else "",
            "OBSERVACIONES": predio.observaciones or "",
        }

        if column_order:
            row = []
            for col_name in column_order:
                col_clean = col_name.strip().upper()
                row.append(header_to_val.get(col_clean, ""))
            return row

        # Orden por defecto definido en el modelo
        return [
            header_to_val["NOMBRE CONJUNTO"],
            header_to_val["NOMBRECALL"],
            header_to_val["PLACAUNIDA"],
            header_to_val["NUM_CASAS"],
            header_to_val["APTOS"],
            header_to_val["LOCALES"],
            header_to_val["PISOS"],
            header_to_val["BARRIO"],
            header_to_val["INT"],
            header_to_val["NOMBRECALLANT2"],
            header_to_val["PLACAUNIDAANT2"],
            header_to_val["NOMBRECALLANT3"],
            header_to_val["PLACAUNIDAANT3"],
            header_to_val["DISTRIBUCION"],
            header_to_val["AMP"],
            header_to_val["CORDX"],
            header_to_val["CORDY"],
        ]

    @classmethod
    def sync_predio_to_sharepoint(cls, predio: MappingPredio) -> Dict[str, Any]:
        """
        Sincroniza un predio específico hacia su destino en SharePoint
        (Lista de SharePoint o Archivo Excel) buscando la configuración asignada a su barrio.
        """
        if not predio.barrio:
            msg = "El predio no tiene barrio asignado para resolver el destino en SharePoint."
            predio.sp_sync_error = msg
            predio.save(update_fields=["sp_sync_error"])
            return {"success": False, "reason": "no_barrio", "message": msg}

        barrio_clean = predio.barrio.strip().upper()
        config = SharePointMappingConfig.objects.filter(
            barrio__iexact=barrio_clean,
            activo=True,
        ).first()

        if not config:
            msg = f"No existe configuración activa de SharePoint para el barrio '{barrio_clean}'."
            predio.sp_sync_error = msg
            predio.save(update_fields=["sp_sync_error"])
            return {"success": False, "reason": "no_config", "message": msg}

        # ---------------------------------------------------------
        # DESTINO 1: LISTA DE SHAREPOINT (MICROSOFT LISTS)
        # ---------------------------------------------------------
        if config.tipo_destino == "LISTA":
            if not config.sp_list_id:
                msg = f"La configuración del barrio '{barrio_clean}' no tiene asignado ID de lista (sp_list_id)."
                predio.sp_sync_error = msg
                predio.save(update_fields=["sp_sync_error"])
                return {"success": False, "reason": "incomplete_config", "message": msg}

            try:
                col_map = cls.get_list_columns(config.sp_list_id)
                fields_payload = cls.format_predio_for_list(predio, col_map)
                result = cls.append_item_to_list(config.sp_list_id, fields_payload)

                predio.sp_synced = True
                predio.sp_synced_at = timezone.now()
                predio.sp_sync_error = ""
                predio.save(update_fields=["sp_synced", "sp_synced_at", "sp_sync_error"])

                logger.info(f"Predio {predio.id} ({predio.barrio}) sincronizado exitosamente en lista SharePoint.")
                return {"success": True, "predio_id": predio.id, "barrio": predio.barrio, "sp_item_id": result.get("id")}

            except Exception as exc:
                err_msg = f"Error al sincronizar con lista SharePoint: {str(exc)}"
                logger.error(err_msg, exc_info=True)
                predio.sp_synced = False
                predio.sp_sync_error = err_msg[:500]
                predio.save(update_fields=["sp_synced", "sp_sync_error"])
                return {"success": False, "error": str(exc), "predio_id": predio.id}

        # ---------------------------------------------------------
        # DESTINO 2: ARCHIVO EXCEL (.XLSX)
        # ---------------------------------------------------------
        if not (config.sp_drive_id and config.sp_item_id):
            msg = f"La configuración del barrio '{barrio_clean}' no tiene asignado drive_id / item_id de SharePoint."
            predio.sp_sync_error = msg
            predio.save(update_fields=["sp_sync_error"])
            return {"success": False, "reason": "incomplete_config", "message": msg}

        try:
            try:
                table_cols = cls.get_table_columns(
                    config.sp_drive_id,
                    config.sp_item_id,
                    config.sp_table_name or "Tabla1",
                )
            except Exception:
                table_cols = None

            row_data = cls.format_predio_row(predio, column_order=table_cols)
            cls.append_rows_to_excel(
                drive_id=config.sp_drive_id,
                item_id=config.sp_item_id,
                table_name=config.sp_table_name or "Tabla1",
                rows_values=[row_data],
            )

            predio.sp_synced = True
            predio.sp_synced_at = timezone.now()
            predio.sp_sync_error = ""
            predio.save(update_fields=["sp_synced", "sp_synced_at", "sp_sync_error"])

            logger.info(f"Predio {predio.id} ({predio.barrio}) sincronizado exitosamente en Excel SharePoint.")
            return {"success": True, "predio_id": predio.id, "barrio": predio.barrio}

        except Exception as exc:
            err_msg = f"Error al sincronizar con Excel SharePoint: {str(exc)}"
            logger.error(err_msg, exc_info=True)
            predio.sp_synced = False
            predio.sp_sync_error = err_msg[:500]
            predio.save(update_fields=["sp_synced", "sp_sync_error"])
            return {"success": False, "error": str(exc), "predio_id": predio.id}

    @classmethod
    def sync_batch_by_barrio(cls, barrio: str) -> Dict[str, Any]:
        """
        Sincroniza todos los predios pendientes de un barrio en un solo lote
        (soporta tanto Listas de SharePoint como archivos Excel).
        """
        barrio_clean = (barrio or "").strip().upper()
        config = SharePointMappingConfig.objects.filter(
            barrio__iexact=barrio_clean,
            activo=True,
        ).first()

        if not config:
            return {
                "success": False,
                "reason": "no_config",
                "message": f"Sin configuración activa para el barrio {barrio_clean}",
            }

        pendientes = list(
            MappingPredio.objects.filter(
                barrio__iexact=barrio_clean,
                is_deleted=False,
                sp_synced=False,
            ).order_by("id")[:100]
        )

        if not pendientes:
            return {"success": True, "count": 0, "message": "No hay predios pendientes de sincronizar"}

        # Sincronización en lote hacia Lista de SharePoint
        if config.tipo_destino == "LISTA":
            if not config.sp_list_id:
                return {
                    "success": False,
                    "reason": "incomplete_config",
                    "message": f"Sin sp_list_id configurado para el barrio {barrio_clean}",
                }
            try:
                col_map = cls.get_list_columns(config.sp_list_id)
                now = timezone.now()
                exitosos = []
                for p in pendientes:
                    fields_payload = cls.format_predio_for_list(p, col_map)
                    cls.append_item_to_list(config.sp_list_id, fields_payload)
                    p.sp_synced = True
                    p.sp_synced_at = now
                    p.sp_sync_error = ""
                    exitosos.append(p)

                MappingPredio.objects.bulk_update(
                    exitosos,
                    fields=["sp_synced", "sp_synced_at", "sp_sync_error"],
                )
                return {"success": True, "count": len(exitosos), "barrio": barrio_clean}

            except Exception as exc:
                err_msg = f"Error en sincronización por lote a lista: {str(exc)}"
                logger.error(err_msg, exc_info=True)
                for p in pendientes:
                    p.sp_sync_error = err_msg[:500]
                MappingPredio.objects.bulk_update(pendientes, fields=["sp_sync_error"])
                return {"success": False, "error": str(exc), "count": len(pendientes)}

        # Sincronización en lote hacia Archivo Excel
        if not (config.sp_drive_id and config.sp_item_id):
            return {
                "success": False,
                "reason": "incomplete_config",
                "message": f"Sin sp_drive_id / sp_item_id para el barrio {barrio_clean}",
            }

        try:
            try:
                table_cols = cls.get_table_columns(
                    config.sp_drive_id,
                    config.sp_item_id,
                    config.sp_table_name or "Tabla1",
                )
            except Exception:
                table_cols = None

            rows_values = [cls.format_predio_row(p, column_order=table_cols) for p in pendientes]
            cls.append_rows_to_excel(
                drive_id=config.sp_drive_id,
                item_id=config.sp_item_id,
                table_name=config.sp_table_name or "Tabla1",
                rows_values=rows_values,
            )

            now = timezone.now()
            for p in pendientes:
                p.sp_synced = True
                p.sp_synced_at = now
                p.sp_sync_error = ""

            MappingPredio.objects.bulk_update(
                pendientes,
                fields=["sp_synced", "sp_synced_at", "sp_sync_error"],
            )

            return {"success": True, "count": len(pendientes), "barrio": barrio_clean}

        except Exception as exc:
            err_msg = f"Error en sincronización por lote a Excel: {str(exc)}"
            logger.error(err_msg, exc_info=True)
            for p in pendientes:
                p.sp_sync_error = err_msg[:500]
            MappingPredio.objects.bulk_update(pendientes, fields=["sp_sync_error"])
            return {"success": False, "error": str(exc), "count": len(pendientes)}

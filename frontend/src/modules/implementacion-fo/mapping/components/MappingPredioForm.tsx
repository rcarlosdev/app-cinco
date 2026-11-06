"use client";

import React, { useState, useEffect, useRef, useTransition } from "react";
import {
  MapPin,
  Building2,
  Home,
  Store,
  Layers,
  Save,
  RotateCcw,
  Navigation,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  Sparkles,
  RefreshCw,
} from "lucide-react";
import { toast } from "sonner";
import { mappingPredioService } from "../services/mappingPredio.service";
import { MappingPredio, CuadraCheckResult, DireccionCheckResult } from "../types";
import { AlertaCuadraBanner } from "./AlertaCuadraBanner";
import { AlertaDireccionFlotante } from "./AlertaDireccionFlotante";
import {
  DireccionCamposGroup,
  parsearCalle,
  componerCalle,
  normalizarDireccionTexto,
} from "./DireccionCamposGroup";
import { obtenerGeolocalizacionPrecisa } from "@/utils/geolocation";

interface MappingPredioFormProps {
  predioEditando?: MappingPredio | null;
  onGuardadoExitoso?: (predio: MappingPredio) => void;
  onCancelarEdicion?: () => void;
}

export const MappingPredioForm: React.FC<MappingPredioFormProps> = ({
  predioEditando,
  onGuardadoExitoso,
  onCancelarEdicion,
}) => {
  const [, startTransition] = useTransition();

  // Estados del formulario - Datos generales
  const [nombreConjunto, setNombreConjunto] = useState("");
  const [barrio, setBarrio] = useState("");
  const [loteAmp, setLoteAmp] = useState("");

  // Dirección Principal
  const [tipoVia, setTipoVia] = useState("CL");
  const [numeroVia, setNumeroVia] = useState("");
  const [nombreCalleLibre, setNombreCalleLibre] = useState("");
  const [placaUnidad, setPlacaUnidad] = useState("");
  const [interior, setInterior] = useState("");

  // Conteo de unidades
  const [numCasas, setNumCasas] = useState(0);
  const [numApartamentos, setNumApartamentos] = useState(0);
  const [numLocales, setNumLocales] = useState(0);
  const [numPisos, setNumPisos] = useState(1);

  // Direcciones Alternativas
  const [mostrarAlternas, setMostrarAlternas] = useState(true);
  const [tipoViaAlt2, setTipoViaAlt2] = useState("CL");
  const [numeroViaAlt2, setNumeroViaAlt2] = useState("");
  const [nombreCalleLibreAlt2, setNombreCalleLibreAlt2] = useState("");
  const [placaAlterna2, setPlacaAlterna2] = useState("");

  const [tipoViaAlt3, setTipoViaAlt3] = useState("CL");
  const [numeroViaAlt3, setNumeroViaAlt3] = useState("");
  const [nombreCalleLibreAlt3, setNombreCalleLibreAlt3] = useState("");
  const [placaAlterna3, setPlacaAlterna3] = useState("");

  const [distribucion, setDistribucion] = useState("");
  const [latitud, setLatitud] = useState<string>("");
  const [longitud, setLongitud] = useState<string>("");
  const [observaciones, setObservaciones] = useState("");

  // Barrios existentes en la tabla
  const [barriosSharePoint, setBarriosSharePoint] = useState<Array<{ barrio: string; descripcion?: string }>>([]);
  const [isRefreshingBarrios, setIsRefreshingBarrios] = useState(false);

  // Alertas tempranas y validaciones
  const [cuadraCheck, setCuadraCheck] = useState<CuadraCheckResult | null>(null);
  const [isLoadingCuadraCheck, setIsLoadingCuadraCheck] = useState(false);
  const [direccionCheck, setDireccionCheck] = useState<DireccionCheckResult | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const clearError = (field: string) => {
    setErrors((prev) => {
      if (!prev[field]) return prev;
      const next = { ...prev };
      delete next[field];
      return next;
    });
  };

  // Estado de carga y GPS
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isGettingGps, setIsGettingGps] = useState(false);

  // Derivar nombre de calle principal unificado
  const calleCalculada = componerCalle(tipoVia, numeroVia, nombreCalleLibre);

  // Cargar datos en caso de edición
  useEffect(() => {
    if (predioEditando) {
      setNombreConjunto(predioEditando.nombre_conjunto || "");

      // Parsear dirección principal
      const pPrincipal = parsearCalle(predioEditando.nombre_calle || "");
      setTipoVia(pPrincipal.tipoVia);
      setNumeroVia(pPrincipal.numeroVia);
      setNombreCalleLibre(pPrincipal.nombreCalleLibre);
      setPlacaUnidad(predioEditando.placa_unidad || "");
      setInterior(predioEditando.interior || "");

      // Parsear dirección alterna 2
      const pAlt2 = parsearCalle(predioEditando.calle_alterna_2 || "");
      setTipoViaAlt2(pAlt2.tipoVia);
      setNumeroViaAlt2(pAlt2.numeroVia);
      setNombreCalleLibreAlt2(pAlt2.nombreCalleLibre);
      setPlacaAlterna2(predioEditando.placa_alterna_2 || "");

      // Parsear dirección alterna 3
      const pAlt3 = parsearCalle(predioEditando.calle_alterna_3 || "");
      setTipoViaAlt3(pAlt3.tipoVia);
      setNumeroViaAlt3(pAlt3.numeroVia);
      setNombreCalleLibreAlt3(pAlt3.nombreCalleLibre);
      setPlacaAlterna3(predioEditando.placa_alterna_3 || "");

      setBarrio(predioEditando.barrio || "");
      setLoteAmp(predioEditando.lote_amp || "");
      setNumCasas(predioEditando.num_casas || 0);
      setNumApartamentos(predioEditando.num_apartamentos || 0);
      setNumLocales(predioEditando.num_locales || 0);
      setNumPisos(predioEditando.num_pisos || 1);
      setDistribucion(predioEditando.distribucion || "");
      setLatitud(predioEditando.latitud ? String(predioEditando.latitud) : "");
      setLongitud(predioEditando.longitud ? String(predioEditando.longitud) : "");
      setObservaciones(predioEditando.observaciones || "");

      if (predioEditando.calle_alterna_2 || predioEditando.calle_alterna_3) {
        setMostrarAlternas(true);
      }
      setErrors({});
    }
  }, [predioEditando]);

  // Cargar barrios existentes en la tabla de SharePoint
  useEffect(() => {
    mappingPredioService
      .getBarriosSharePoint()
      .then((items) => setBarriosSharePoint(items))
      .catch(() => { });
  }, []);

  // Alerta temprana: Detección de cuadra o plancha ya levantada
  useEffect(() => {
    if (!barrio.trim() || !loteAmp.trim() || predioEditando) {
      setCuadraCheck(null);
      return;
    }

    const timer = setTimeout(async () => {
      setIsLoadingCuadraCheck(true);
      try {
        const res = await mappingPredioService.verificarCuadra(
          barrio.trim(),
          loteAmp.trim(),
          calleCalculada || undefined,
        );
        setCuadraCheck(res);
      } catch {
        // Silencioso
      } finally {
        setIsLoadingCuadraCheck(false);
      }
    }, 600);

    return () => clearTimeout(timer);
  }, [barrio, loteAmp, calleCalculada, predioEditando]);

  // Alerta de dirección duplicada
  useEffect(() => {
    const placaNorm = normalizarDireccionTexto(placaUnidad);
    if (!calleCalculada || !placaNorm) {
      setDireccionCheck(null);
      return;
    }

    const timer = setTimeout(async () => {
      try {
        const res = await mappingPredioService.verificarDireccion(
          calleCalculada,
          placaNorm,
          interior.trim() || undefined,
          predioEditando?.id,
        );
        setDireccionCheck(res);
      } catch {
        // Silencioso
      }
    }, 500);

    return () => clearTimeout(timer);
  }, [calleCalculada, placaUnidad, interior, predioEditando]);

  // Captura satelital de GPS de alta precisión en 1 clic
  const handleObtenerGps = async () => {
    if (typeof window === "undefined" || !navigator.geolocation) {
      toast.error("La geolocalización no es soportada por este navegador");
      return;
    }

    setIsGettingGps(true);
    const toastId = toast.loading("Obteniendo ubicación... lectura 1/4...");

    try {
      const res = await obtenerGeolocalizacionPrecisa({
        maxIntentos: 4,
        umbralPrecision: 15,
        timeoutPorIntento: 7000,
        onProgreso: ({ intento, maxIntentos, precisionActual }) => {
          const textoPrecision =
            precisionActual !== undefined ? ` (precisión actual ±${precisionActual}m)` : "";
          toast.loading(
            `Obteniendo ubicación... lectura ${intento}/${maxIntentos}${textoPrecision}...`,
            { id: toastId }
          );
        },
      });

      const lat = res.latitud.toFixed(6);
      const lng = res.longitud.toFixed(6);
      setLatitud(lat);
      setLongitud(lng);
      clearError("latitud");
      clearError("longitud");

      if (res.esOptima) {
        toast.success(`GPS capturado con precisión óptima de ±${res.precision}m`, {
          id: toastId,
          description: `Lat: ${lat}, Long: ${lng}`,
        });
      } else {
        toast.warning(`GPS capturado con precisión de ±${res.precision}m`, {
          id: toastId,
          description: `Lat: ${lat}, Long: ${lng}`,
        });
      }
    } catch (error: any) {
      toast.error(error.message || "No se pudo obtener la ubicación GPS.", { id: toastId });
    } finally {
      setIsGettingGps(false);
    }
  };

  const handleActualizarBarrios = async () => {
    setIsRefreshingBarrios(true);
    const toastId = toast.loading("Actualizando barrios desde SharePoint...");
    try {
      const res = await mappingPredioService.autoDescubrirBarriosSharePoint();
      if (res.success) {
        const items = await mappingPredioService.getBarriosSharePoint();
        setBarriosSharePoint(items);

        const nuevasListas = res.listas?.creadas || 0;
        if (nuevasListas > 0) {
          toast.success(`Se encontraron ${nuevasListas} nueva(s) lista(s) en SharePoint`, {
            id: toastId,
            description: `${items.length} listas de barrios disponibles`,
          });
        } else {
          toast.success("Listas de SharePoint actualizadas", {
            id: toastId,
            description: `${items.length} listas disponibles`,
          });
        }
      } else {
        toast.error(res.error || "No se pudieron actualizar los barrios", { id: toastId });
      }
    } catch (err: any) {
      toast.error(
        err?.response?.data?.error ||
        err?.message ||
        "Error al conectar con SharePoint para actualizar barrios",
        { id: toastId }
      );
    } finally {
      setIsRefreshingBarrios(false);
    }
  };

  const handleLimpiarFormulario = () => {
    setNombreConjunto("");
    setTipoVia("CL");
    setNumeroVia("");
    setNombreCalleLibre("");
    setPlacaUnidad("");
    setInterior("");
    setBarrio("");
    setLoteAmp("");
    setNumCasas(0);
    setNumApartamentos(0);
    setNumLocales(0);
    setNumPisos(1);
    setTipoViaAlt2("CL");
    setNumeroViaAlt2("");
    setNombreCalleLibreAlt2("");
    setPlacaAlterna2("");
    setTipoViaAlt3("CL");
    setNumeroViaAlt3("");
    setNombreCalleLibreAlt3("");
    setPlacaAlterna3("");
    setDistribucion("");
    setLatitud("");
    setLongitud("");
    setObservaciones("");
    setCuadraCheck(null);
    setDireccionCheck(null);
    setErrors({});
  };

  const validateForm = (): Record<string, string> => {
    const newErrors: Record<string, string> = {};

    if (!barrio.trim()) {
      newErrors.barrio = "El barrio es obligatorio.";
    }

    if (!loteAmp.trim()) {
      newErrors.loteAmp = "El AMP / lote de plancha es obligatorio.";
    }

    if (tipoVia === "OTRO") {
      if (!nombreCalleLibre.trim()) {
        newErrors.via = "Ingresa la vía o dirección completa.";
      }
    } else {
      if (!numeroVia.trim()) {
        newErrors.via = "Ingresa el número o letra de la vía.";
      }
    }

    if (!placaUnidad.trim() && !nombreConjunto.trim()) {
      newErrors.placa = "Ingresa la placa del predio o el nombre del conjunto.";
    }

    if (direccionCheck?.existe_exacta) {
      newErrors.placa = "Dirección duplicada";
    }

    // Coordenadas GPS obligatorias
    if (!latitud.trim()) {
      newErrors.latitud = "La latitud es obligatoria. Puedes tomarla con el GPS.";
    } else {
      const latNum = Number(latitud.replace(",", "."));
      if (isNaN(latNum) || latNum < -90 || latNum > 90) {
        newErrors.latitud = "Ingresa una latitud válida (ej: 6.308625).";
      }
    }

    if (!longitud.trim()) {
      newErrors.longitud = "La longitud es obligatoria. Puedes tomarla con el GPS.";
    } else {
      const lngNum = Number(longitud.replace(",", "."));
      if (isNaN(lngNum) || lngNum < -180 || lngNum > 180) {
        newErrors.longitud = "Ingresa una longitud válida (ej: -75.545410).";
      }
    }

    return newErrors;
  };

  const handleSubmit = async () => {
    // Validar campos obligatorios al estilo del módulo de actividades
    const formErrors = validateForm();
    if (Object.keys(formErrors).length > 0) {
      setErrors(formErrors);
      const firstMessage = Object.values(formErrors)[0];
      toast.error(
        firstMessage || "Completa los campos obligatorios antes de guardar."
      );
      return;
    }

    // Bloqueo adicional por dirección duplicada
    if (direccionCheck?.existe_exacta) {
      toast.error("Dirección duplicada");
      return;
    }

    setIsSubmitting(true);

    const calleAlt2 = componerCalle(tipoViaAlt2, numeroViaAlt2, nombreCalleLibreAlt2);
    const calleAlt3 = componerCalle(tipoViaAlt3, numeroViaAlt3, nombreCalleLibreAlt3);
    const placaPrincipal = normalizarDireccionTexto(placaUnidad);
    const placaAlt2 = normalizarDireccionTexto(placaAlterna2);
    const placaAlt3 = normalizarDireccionTexto(placaAlterna3);

    const payload: Partial<MappingPredio> = {
      nombre_conjunto: nombreConjunto.trim().toUpperCase(),
      nombre_calle: calleCalculada,
      placa_unidad: placaPrincipal,
      interior: interior.trim().toUpperCase(),
      barrio: barrio.trim().toUpperCase(),
      lote_amp: loteAmp.trim().toUpperCase(),
      num_casas: Number(numCasas) || 0,
      num_apartamentos: Number(numApartamentos) || 0,
      num_locales: Number(numLocales) || 0,
      num_pisos: Math.max(1, Number(numPisos) || 1),
      calle_alterna_2: calleAlt2,
      placa_alterna_2: (calleAlt2 || placaAlt2) ? placaAlt2 : "",
      calle_alterna_3: calleAlt3,
      placa_alterna_3: (calleAlt3 || placaAlt3) ? placaAlt3 : "",
      distribucion: distribucion.trim().toUpperCase(),
      latitud: latitud ? String(latitud).replace(",", ".") : null,
      longitud: longitud ? String(longitud).replace(",", ".") : null,
      observaciones: observaciones.trim(),
    };

    try {
      let resultado: MappingPredio;
      if (predioEditando) {
        resultado = await mappingPredioService.actualizar(predioEditando.id, payload);
        toast.success("Predio actualizado exitosamente");
      } else {
        resultado = await mappingPredioService.crear(payload);
        toast.success("Predio registrado correctamente", {
          description: `${resultado.direccion_completa} (${resultado.total_unidades} unidades)`,
        });
      }

      handleLimpiarFormulario();

      if (onGuardadoExitoso) {
        onGuardadoExitoso(resultado);
      }
    } catch (error: any) {
      const errorMsg =
        error?.response?.data?.detail ||
        error?.message ||
        "No se pudo guardar el predio. Revisa los datos.";
      toast.error(errorMsg);
    } finally {
      setIsSubmitting(false);
    }
  };

  const totalUnidades = (Number(numCasas) || 0) + (Number(numApartamentos) || 0) + (Number(numLocales) || 0);

  return (
    <form
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        handleSubmit();
      }}
      className="space-y-6"
    >
      {/* Banner de alerta temprana si la cuadra o plancha ya fue censada */}
      <AlertaCuadraBanner
        checkResult={cuadraCheck}
        isLoading={isLoadingCuadraCheck}
        onIgnorar={() => setCuadraCheck(null)}
      />

      {/* Alerta de dirección repetida no bloqueante */}
      <AlertaDireccionFlotante checkResult={direccionCheck} />

      {/* SECCIÓN 1: UBICACIÓN Y PLANCHA (AMP) */}
      <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-xs dark:border-gray-800 dark:bg-gray-900">
        <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-gray-800 dark:text-gray-200">
          <MapPin className="h-4 w-4 text-brand-500 dark:text-brand-400" />
          1. Sector y Plancha Cartográfica
        </h3>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          {/* Selector de Barrio existente en la tabla */}
          <div>
            <div className="flex items-center justify-between">
              <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300">
                Barrio <strong className="text-red-400">*</strong>
              </label>
              <button
                type="button"
                onClick={handleActualizarBarrios}
                disabled={isRefreshingBarrios}
                title="Sincronizar y escanear nuevas listas o archivos en SharePoint"
                className="inline-flex items-center gap-1 text-[11px] font-medium text-brand-600 hover:text-brand-700 hover:underline disabled:opacity-50 dark:text-brand-400 dark:hover:text-brand-300 transition-colors"
              >
                <RefreshCw className={`h-3 w-3 ${isRefreshingBarrios ? "animate-spin" : ""}`} />
                {isRefreshingBarrios ? "Actualizando..." : "Actualizar barrios"}
              </button>
            </div>
            <select
              value={barrio}
              onChange={(e) => {
                setBarrio(e.target.value);
                clearError("barrio");
              }}
              className={`mt-1 w-full rounded-lg border bg-white px-3 py-2 text-sm font-medium focus:ring-2 focus:outline-hidden dark:bg-gray-800 dark:text-white ${
                errors.barrio
                  ? "border-red-500 text-red-900 focus:border-red-500 focus:ring-red-500/20 dark:border-red-500 dark:text-red-200"
                  : "border-gray-300 text-gray-800 focus:border-brand-500 focus:ring-brand-500/20 dark:border-gray-700"
              }`}
            >
              <option value="">
                {isRefreshingBarrios
                  ? "Escaneando SharePoint..."
                  : barriosSharePoint.length === 0
                  ? "Cargando barrios..."
                  : "-- Selecciona el barrio --"}
              </option>
              {barriosSharePoint.map((b) => (
                <option key={b.barrio} value={b.barrio}>
                  {b.barrio}
                </option>
              ))}
              {/* Preservar opción si se está editando un registro con un barrio no presente */}
              {barrio && !barriosSharePoint.some((b) => b.barrio === barrio) && (
                <option value={barrio}>{barrio}</option>
              )}
            </select>
            {errors.barrio && (
              <p className="mt-1 text-xs text-red-500 dark:text-red-400">
                {errors.barrio}
              </p>
            )}
          </div>

          {/* Lote / Plancha AMP */}
          <div>
            <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300">
              AMP <strong className="text-red-400">*</strong>
            </label>
            <input
              type="text"
              value={loteAmp}
              onChange={(e) => {
                setLoteAmp(e.target.value.toUpperCase());
                clearError("loteAmp");
              }}
              placeholder="Ej: 1, 102A, MZ-4"
              className={`mt-1 w-full rounded-lg border bg-white px-3 py-2 text-sm uppercase placeholder:normal-case focus:ring-2 focus:outline-hidden dark:bg-gray-800 dark:text-white ${
                errors.loteAmp
                  ? "border-red-500 text-red-900 focus:border-red-500 focus:ring-red-500/20 dark:border-red-500 dark:text-red-200"
                  : "border-gray-300 text-gray-900 focus:border-brand-500 focus:ring-brand-500/20 dark:border-gray-700"
              }`}
            />
            {errors.loteAmp ? (
              <p className="mt-1 text-xs text-red-500 dark:text-red-400">
                {errors.loteAmp}
              </p>
            ) : (
              <span className="text-[11px] text-gray-500">Lote marcado en la plancha de campo</span>
            )}
          </div>

          {/* Nombre Conjunto / Edificio */}
          <div>
            <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300">
              Nombre Conjunto
            </label>
            <input
              type="text"
              value={nombreConjunto}
              onChange={(e) => {
                setNombreConjunto(e.target.value.toUpperCase());
                clearError("placa");
              }}
              placeholder="Ej: EDIFICIO NUEVO MILENIUM"
              className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm uppercase placeholder:normal-case focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 focus:outline-hidden dark:border-gray-700 dark:bg-gray-800 dark:text-white"
            />
          </div>
        </div>
      </div>

      {/* SECCIÓN 2: DIRECCIÓN PRINCIPAL */}
      <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-xs dark:border-gray-800 dark:bg-gray-900">
        <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-gray-800 dark:text-gray-200">
          <Navigation className="h-4 w-4 text-brand-500 dark:text-brand-400" />
          2. Dirección Principal del Mapping
        </h3>

        <DireccionCamposGroup
          tipoVia={tipoVia}
          onTipoViaChange={setTipoVia}
          numeroVia={numeroVia}
          onNumeroViaChange={(val) => {
            setNumeroVia(val);
            clearError("via");
          }}
          nombreCalleLibre={nombreCalleLibre}
          onNombreCalleLibreChange={(val) => {
            setNombreCalleLibre(val);
            clearError("via");
          }}
          placa={placaUnidad}
          onPlacaChange={(val) => {
            setPlacaUnidad(val);
            clearError("placa");
          }}
          interior={interior}
          onInteriorChange={setInterior}
          mostrarInterior={true}
          esObligatoria={true}
          errorVia={!!errors.via}
          hintVia={errors.via}
          errorPlaca={!!errors.placa}
          hintPlaca={errors.placa}
          labelVia="Número / Letra de la Vía"
          labelPlaca="Placa / Número (PLACAUNIDA)"
        />
      </div>

      {/* SECCIÓN 3: CONTEO DE INMUEBLES Y PISOS */}
      <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-xs dark:border-gray-800 dark:bg-gray-900">
        <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-gray-800 dark:text-gray-200">
          <Building2 className="h-4 w-4 text-brand-500 dark:text-brand-400" />
          3. Tipología y Conteo de Inmuebles
        </h3>

        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          {/* Casas */}
          <div className="rounded-xl border border-gray-200 bg-gray-50/60 p-3.5 dark:border-gray-800 dark:bg-gray-800/40">
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-1.5 text-xs font-semibold text-gray-700 dark:text-gray-300">
                <Home className="h-3.5 w-3.5 text-brand-500" />
                Casas
              </span>
            </div>
            <div className="mt-2 flex items-center justify-between">
              <button
                type="button"
                onClick={() => setNumCasas(Math.max(0, numCasas - 1))}
                className="flex h-8 w-8 items-center justify-center rounded-lg border border-gray-300 bg-white text-base font-bold hover:bg-gray-100 active:scale-95 dark:border-gray-700 dark:bg-gray-800 dark:text-white dark:hover:bg-gray-700"
              >
                -
              </button>
              <input
                type="number"
                min="0"
                value={numCasas}
                onChange={(e) => setNumCasas(Math.max(0, parseInt(e.target.value) || 0))}
                className="w-16 text-center text-base font-bold text-gray-900 focus:outline-hidden dark:text-white"
              />
              <button
                type="button"
                onClick={() => setNumCasas(numCasas + 1)}
                className="flex h-8 w-8 items-center justify-center rounded-lg border border-gray-300 bg-white text-base font-bold hover:bg-gray-100 active:scale-95 dark:border-gray-700 dark:bg-gray-800 dark:text-white dark:hover:bg-gray-700"
              >
                +
              </button>
            </div>
          </div>

          {/* Apartamentos */}
          <div className="rounded-xl border border-gray-200 bg-gray-50/60 p-3.5 dark:border-gray-800 dark:bg-gray-800/40">
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-1.5 text-xs font-semibold text-gray-700 dark:text-gray-300">
                <Building2 className="h-3.5 w-3.5 text-brand-600" />
                Apartamentos
              </span>
            </div>
            <div className="mt-2 flex items-center justify-between">
              <button
                type="button"
                onClick={() => setNumApartamentos(Math.max(0, numApartamentos - 1))}
                className="flex h-8 w-8 items-center justify-center rounded-lg border border-gray-300 bg-white text-base font-bold hover:bg-gray-100 active:scale-95 dark:border-gray-700 dark:bg-gray-800 dark:text-white dark:hover:bg-gray-700"
              >
                -
              </button>
              <input
                type="number"
                min="0"
                value={numApartamentos}
                onChange={(e) => setNumApartamentos(Math.max(0, parseInt(e.target.value) || 0))}
                className="w-16 text-center text-base font-bold text-gray-900 focus:outline-hidden dark:text-white"
              />
              <button
                type="button"
                onClick={() => setNumApartamentos(numApartamentos + 1)}
                className="flex h-8 w-8 items-center justify-center rounded-lg border border-gray-300 bg-white text-base font-bold hover:bg-gray-100 active:scale-95 dark:border-gray-700 dark:bg-gray-800 dark:text-white dark:hover:bg-gray-700"
              >
                +
              </button>
            </div>
          </div>

          {/* Locales */}
          <div className="rounded-xl border border-gray-200 bg-gray-50/60 p-3.5 dark:border-gray-800 dark:bg-gray-800/40">
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-1.5 text-xs font-semibold text-gray-700 dark:text-gray-300">
                <Store className="h-3.5 w-3.5 text-emerald-600" />
                Locales
              </span>
            </div>
            <div className="mt-2 flex items-center justify-between">
              <button
                type="button"
                onClick={() => setNumLocales(Math.max(0, numLocales - 1))}
                className="flex h-8 w-8 items-center justify-center rounded-lg border border-gray-300 bg-white text-base font-bold hover:bg-gray-100 active:scale-95 dark:border-gray-700 dark:bg-gray-800 dark:text-white dark:hover:bg-gray-700"
              >
                -
              </button>
              <input
                type="number"
                min="0"
                value={numLocales}
                onChange={(e) => setNumLocales(Math.max(0, parseInt(e.target.value) || 0))}
                className="w-16 text-center text-base font-bold text-gray-900 focus:outline-hidden dark:text-white"
              />
              <button
                type="button"
                onClick={() => setNumLocales(numLocales + 1)}
                className="flex h-8 w-8 items-center justify-center rounded-lg border border-gray-300 bg-white text-base font-bold hover:bg-gray-100 active:scale-95 dark:border-gray-700 dark:bg-gray-800 dark:text-white dark:hover:bg-gray-700"
              >
                +
              </button>
            </div>
          </div>

          {/* Pisos */}
          <div className="rounded-xl border border-gray-200 bg-gray-50/60 p-3.5 dark:border-gray-800 dark:bg-gray-800/40">
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-1.5 text-xs font-semibold text-gray-700 dark:text-gray-300">
                <Layers className="h-3.5 w-3.5 text-brand-700" />
                Pisos
              </span>
            </div>
            <div className="mt-2 flex items-center justify-between">
              <button
                type="button"
                onClick={() => setNumPisos(Math.max(1, numPisos - 1))}
                className="flex h-8 w-8 items-center justify-center rounded-lg border border-gray-300 bg-white text-base font-bold hover:bg-gray-100 active:scale-95 dark:border-gray-700 dark:bg-gray-800 dark:text-white dark:hover:bg-gray-700"
              >
                -
              </button>
              <input
                type="number"
                min="1"
                value={numPisos}
                onChange={(e) => setNumPisos(Math.max(1, parseInt(e.target.value) || 1))}
                className="w-16 text-center text-base font-bold text-gray-900 focus:outline-hidden dark:text-white"
              />
              <button
                type="button"
                onClick={() => setNumPisos(numPisos + 1)}
                className="flex h-8 w-8 items-center justify-center rounded-lg border border-gray-300 bg-white text-base font-bold hover:bg-gray-100 active:scale-95 dark:border-gray-700 dark:bg-gray-800 dark:text-white dark:hover:bg-gray-700"
              >
                +
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* SECCIÓN 4: DISTRIBUCIÓN Y GEORREFERENCIACIÓN (GPS) */}
      <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-xs dark:border-gray-800 dark:bg-gray-900">
        <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-gray-800 dark:text-gray-200">
          <MapPin className="h-4 w-4 text-brand-500 dark:text-brand-400" />
          4. Distribución Interna y Coordenadas GPS
        </h3>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {/* Distribución */}
          <div className="sm:col-span-2">
            <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300">
              Distribución Interna
            </label>
            <input
              type="text"
              value={distribucion}
              onChange={(e) => setDistribucion(e.target.value.toUpperCase())}
              placeholder="Ej: AP 101-102-103-201-202-203 o LC 1-2"
              className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm uppercase placeholder:normal-case focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 focus:outline-hidden dark:border-gray-700 dark:bg-gray-800 dark:text-white"
            />
          </div>

          {/* Latitud (CORDX) */}
          <div>
            <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300">
              Latitud (CORDX) <strong className="text-red-400">*</strong>
            </label>
            <input
              type="text"
              value={latitud}
              onChange={(e) => {
                setLatitud(e.target.value);
                clearError("latitud");
              }}
              placeholder="Ej: 6.308625"
              className={`mt-1 w-full rounded-lg border bg-white px-3 py-2 text-sm font-mono focus:ring-2 focus:outline-hidden dark:bg-gray-800 dark:text-white ${
                errors.latitud
                  ? "border-red-500 text-red-900 focus:border-red-500 focus:ring-red-500/20 dark:border-red-500 dark:text-red-200"
                  : "border-gray-300 text-gray-900 focus:border-brand-500 focus:ring-brand-500/20 dark:border-gray-700"
              }`}
            />
            {errors.latitud && (
              <p className="mt-1 text-xs text-red-500 dark:text-red-400">
                {errors.latitud}
              </p>
            )}
          </div>

          {/* Longitud (CORDY) */}
          <div>
            <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300">
              Longitud (CORDY) <strong className="text-red-400">*</strong>
            </label>
            <input
              type="text"
              value={longitud}
              onChange={(e) => {
                setLongitud(e.target.value);
                clearError("longitud");
              }}
              placeholder="Ej: -75.545410"
              className={`mt-1 w-full rounded-lg border bg-white px-3 py-2 text-sm font-mono focus:ring-2 focus:outline-hidden dark:bg-gray-800 dark:text-white ${
                errors.longitud
                  ? "border-red-500 text-red-900 focus:border-red-500 focus:ring-red-500/20 dark:border-red-500 dark:text-red-200"
                  : "border-gray-300 text-gray-900 focus:border-brand-500 focus:ring-brand-500/20 dark:border-gray-700"
              }`}
            />
            {errors.longitud && (
              <p className="mt-1 text-xs text-red-500 dark:text-red-400">
                {errors.longitud}
              </p>
            )}
          </div>
        </div>

        {/* Botones de acción GPS */}
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={handleObtenerGps}
            disabled={isGettingGps}
            className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-3.5 py-2 text-xs font-bold text-white shadow-xs hover:bg-emerald-700 active:scale-95 disabled:opacity-50 transition-all"
          >
            {isGettingGps ? (
              <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
            ) : (
              <Navigation className="h-4 w-4" />
            )}
            Tomar Ubicación Actual
          </button>

          {latitud && longitud && (
            <a
              href={`https://www.google.com/maps?q=${latitud},${longitud}`}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-3 py-2 text-xs font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300"
            >
              <ExternalLink className="h-3.5 w-3.5 text-brand-500" />
              Verificar en Google Maps
            </a>
          )}
        </div>
      </div>

      {/* SECCIÓN 5: DIRECCIONES ALTERNATIVAS (COLAPSABLE / ACORDEÓN) */}
      <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-xs dark:border-gray-800 dark:bg-gray-900">
        <button
          type="button"
          onClick={() => setMostrarAlternas(!mostrarAlternas)}
          className="flex w-full items-center justify-between text-left"
        >
          <span className="text-sm font-semibold uppercase tracking-wider text-gray-800 dark:text-gray-200">
            5. Direcciones Alternativas
          </span>
          <span className="rounded-md border border-gray-200 bg-gray-100 p-1 text-gray-600 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300">
            {mostrarAlternas ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </span>
        </button>

        {mostrarAlternas && (
          <div className="mt-4 space-y-5 pt-3 border-t border-gray-100 dark:border-gray-800">
            {/* Alterna 2 */}
            <div className="rounded-lg border border-gray-100 bg-gray-50/50 p-4 dark:border-gray-800/80 dark:bg-gray-800/30">
              <span className="mb-3 block text-xs font-bold uppercase tracking-wider text-gray-600 dark:text-gray-400">
                Dirección Alternativa 2
              </span>
              <DireccionCamposGroup
                tipoVia={tipoViaAlt2}
                onTipoViaChange={setTipoViaAlt2}
                numeroVia={numeroViaAlt2}
                onNumeroViaChange={setNumeroViaAlt2}
                nombreCalleLibre={nombreCalleLibreAlt2}
                onNombreCalleLibreChange={setNombreCalleLibreAlt2}
                placa={placaAlterna2}
                onPlacaChange={setPlacaAlterna2}
                mostrarInterior={false}
                esObligatoria={false}
                labelVia="Vía Alternativa 2"
                labelPlaca="Placa Alternativa 2"
              />
            </div>

            {/* Alterna 3 */}
            <div className="rounded-lg border border-gray-100 bg-gray-50/50 p-4 dark:border-gray-800/80 dark:bg-gray-800/30">
              <span className="mb-3 block text-xs font-bold uppercase tracking-wider text-gray-600 dark:text-gray-400">
                Dirección Alternativa 3
              </span>
              <DireccionCamposGroup
                tipoVia={tipoViaAlt3}
                onTipoViaChange={setTipoViaAlt3}
                numeroVia={numeroViaAlt3}
                onNumeroViaChange={setNumeroViaAlt3}
                nombreCalleLibre={nombreCalleLibreAlt3}
                onNombreCalleLibreChange={setNombreCalleLibreAlt3}
                placa={placaAlterna3}
                onPlacaChange={setPlacaAlterna3}
                mostrarInterior={false}
                esObligatoria={false}
                labelVia="Vía Alternativa 3"
                labelPlaca="Placa Alternativa 3"
              />
            </div>
          </div>
        )}
      </div>

      {/* BOTONES PRINCIPALES DE ACCIÓN */}
      <div className="sticky bottom-3 z-20 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-gray-200 bg-white/95 p-4 shadow-lg backdrop-blur-md dark:border-gray-800 dark:bg-gray-900/95">
        <div className="flex items-center gap-2">
          {predioEditando ? (
            <button
              type="button"
              onClick={onCancelarEdicion}
              className="inline-flex items-center gap-2 rounded-lg bg-white px-4 py-2.5 text-xs font-semibold text-gray-700 ring-1 ring-inset ring-gray-300 hover:bg-gray-50 dark:bg-gray-800 dark:text-gray-300 dark:ring-gray-700 dark:hover:bg-white/[0.03] dark:hover:text-white transition-all shadow-xs"
            >
              Cancelar Edición
            </button>
          ) : (
            <button
              type="button"
              onClick={handleLimpiarFormulario}
              className="inline-flex items-center gap-2 rounded-lg bg-white px-3.5 py-2.5 text-xs font-semibold text-gray-700 ring-1 ring-inset ring-gray-300 hover:bg-gray-50 dark:bg-gray-800 dark:text-gray-300 dark:ring-gray-700 dark:hover:bg-white/[0.03] dark:hover:text-white transition-all shadow-xs"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              Limpiar Campos
            </button>
          )}
        </div>

        <div className="flex items-center gap-2.5">
          <button
            type="submit"
            disabled={isSubmitting || Boolean(direccionCheck?.existe_exacta)}
            title={direccionCheck?.existe_exacta ? "Dirección duplicada" : undefined}
            className="inline-flex items-center gap-2 rounded-lg bg-brand-500 px-5 py-2.5 text-xs font-bold text-white shadow-md hover:bg-brand-600 active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
          >
            {isSubmitting ? (
              <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
            ) : (
              <Save className="h-4 w-4" />
            )}
            {predioEditando ? "Actualizar" : "Guardar"}
          </button>
        </div>
      </div>
    </form>
  );
};

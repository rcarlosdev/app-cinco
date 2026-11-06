// src/utils/geolocation.ts
/**
 * Utilidades para geolocalización de alta precisión en navegador.
 * Realiza múltiples lecturas progresivas para dar tiempo a que el hardware GPS
 * enganche satélites reales, optimizando el umbral de precisión.
 */

export interface OpcionesGeolocalizacion {
  maxIntentos?: number;
  umbralPrecision?: number; // margen de error óptimo en metros (ej: 15)
  timeoutPorIntento?: number; // tiempo de espera en milisegundos por intento (ej: 7000)
  onProgreso?: (info: {
    intento: number;
    maxIntentos: number;
    precisionActual?: number;
  }) => void;
}

export interface ResultadoGeolocalizacion {
  geolocalizacionActivada: boolean;
  latitud: number;
  longitud: number;
  precision: number;
  intentos: number;
  esOptima: boolean;
  advertencia?: string;
}

/**
 * Traduce códigos de error nativos de Geolocation API a mensajes claros en español.
 */
export const mapearErrorGeolocalizacion = (error: GeolocationPositionError): string => {
  switch (error.code) {
    case error.PERMISSION_DENIED:
      return "Permiso de ubicación denegado en el navegador.";
    case error.POSITION_UNAVAILABLE:
      return "Señal de GPS / ubicación no disponible en este momento.";
    case error.TIMEOUT:
      return "Tiempo de espera agotado al buscar satélites de ubicación.";
    default:
      return error.message || "Error desconocido al obtener la geolocalización.";
  }
};

/**
 * Obtiene las coordenadas GPS del dispositivo con alta precisión mediante lecturas escalonadas.
 */
export const obtenerGeolocalizacionPrecisa = (
  opciones: OpcionesGeolocalizacion = {}
): Promise<ResultadoGeolocalizacion> => {
  const {
    maxIntentos = 4,
    umbralPrecision = 15,
    timeoutPorIntento = 7000,
    onProgreso,
  } = opciones;

  return new Promise((resolve, reject) => {
    if (typeof window === "undefined" || !navigator.geolocation) {
      return reject(new Error("La geolocalización no es soportada por este navegador."));
    }

    const geoOptions: PositionOptions = {
      enableHighAccuracy: true,
      timeout: timeoutPorIntento,
      maximumAge: 0,
    };

    let intento = 0;
    let mejorPrecision = Infinity;
    let mejorPosicion: GeolocationPosition | null = null;

    const intentar = () => {
      intento++;

      if (onProgreso) {
        onProgreso({
          intento,
          maxIntentos,
          precisionActual: mejorPosicion ? Math.round(mejorPrecision) : undefined,
        });
      }

      navigator.geolocation.getCurrentPosition(
        (pos) => {
          const { latitude, longitude, accuracy } = pos.coords;

          if (accuracy < mejorPrecision) {
            mejorPrecision = accuracy;
            mejorPosicion = pos;
          }

          if (onProgreso) {
            onProgreso({
              intento,
              maxIntentos,
              precisionActual: Math.round(accuracy),
            });
          }

          // Si la precisión actual cumple o supera el umbral deseado (<= 15m), terminamos exitosamente
          if (accuracy <= umbralPrecision) {
            return resolve({
              geolocalizacionActivada: true,
              latitud: latitude,
              longitud: longitude,
              precision: Math.round(accuracy),
              intentos: intento,
              esOptima: true,
            });
          }

          // Si aún quedan intentos disponibles, esperamos un breve momento para que mejore la señal satelital
          if (intento < maxIntentos) {
            setTimeout(intentar, 600);
          } else if (mejorPosicion) {
            // Se agotaron los intentos: entregamos la mejor lectura obtenida
            return resolve({
              geolocalizacionActivada: true,
              latitud: mejorPosicion.coords.latitude,
              longitud: mejorPosicion.coords.longitude,
              precision: Math.round(mejorPrecision),
              intentos: intento,
              esOptima: false,
              advertencia: `Precisión obtenida: ±${Math.round(mejorPrecision)}m`,
            });
          } else {
            return reject(new Error("No se pudo obtener una ubicación GPS."));
          }
        },
        (err) => {
          if (intento < maxIntentos) {
            setTimeout(intentar, 600);
          } else if (mejorPosicion) {
            return resolve({
              geolocalizacionActivada: true,
              latitud: mejorPosicion.coords.latitude,
              longitud: mejorPosicion.coords.longitude,
              precision: Math.round(mejorPrecision),
              intentos: intento,
              esOptima: false,
              advertencia: `Precisión obtenida: ±${Math.round(mejorPrecision)}m`,
            });
          } else {
            return reject(new Error(mapearErrorGeolocalizacion(err)));
          }
        },
        geoOptions
      );
    };

    intentar();
  });
};

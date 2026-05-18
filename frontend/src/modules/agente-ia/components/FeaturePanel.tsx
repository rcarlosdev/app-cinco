"use client";

const estados = [
  ["Completado", "La tarea termino y el informe ya refleja la evidencia."],
  ["Bloqueado", "Hace falta una condicion de negocio o una policy impide continuar."],
  ["Requiere aclaracion", "La consulta necesita mas precision para evitar errores."],
  ["Esperando aprobacion", "Existe una accion pausada hasta recibir approval."],
  ["En ejecucion", "La tarea sigue validando o reuniendo evidencia."],
  ["Fallido", "Ocurrio un problema y la respuesta intenta explicarlo en lenguaje claro."],
];

const ejemplos = [
  "Inventario por cuadrilla TIRAN224",
  "Kardex del tecnico 5098747",
  "Empleados por area",
  "Ausentismo de los ultimos 15 dias",
];

const limites = [
  "No expone JSON crudo, prompts internos ni SQL sensible.",
  "Si falta contexto, pedira aclaracion antes de inventar una respuesta.",
  "No fuerza graficos cuando la evidencia es mejor como tabla operativa.",
];

const FeaturePanel = () => {
  return (
    <div className="space-y-4 text-sm">
      <section className="rounded-2xl border border-gray-200 bg-gray-50 p-4 dark:border-gray-800 dark:bg-gray-900">
        <div className="font-semibold text-gray-900 dark:text-white">
          Que puede hacer
        </div>
        <div className="mt-3 space-y-2 text-gray-600 dark:text-gray-300">
          <div>Responder consultas empresariales por dominio con evidencia visible.</div>
          <div>Mostrar resumen ejecutivo, KPIs, tablas, timeline y limitaciones.</div>
          <div>Separar conversacion a la izquierda e informe empresarial a la derecha.</div>
        </div>
      </section>

      <section className="rounded-2xl border border-gray-200 bg-gray-50 p-4 dark:border-gray-800 dark:bg-gray-900">
        <div className="font-semibold text-gray-900 dark:text-white">
          Ejemplos de consulta
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          {ejemplos.map((example) => (
            <span
              key={example}
              className="rounded-full border border-gray-200 bg-white px-3 py-1 text-xs text-gray-700 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-200"
            >
              {example}
            </span>
          ))}
        </div>
      </section>

      <section className="rounded-2xl border border-gray-200 bg-gray-50 p-4 dark:border-gray-800 dark:bg-gray-900">
        <div className="font-semibold text-gray-900 dark:text-white">
          Limites conocidos
        </div>
        <div className="mt-3 space-y-2 text-gray-600 dark:text-gray-300">
          {limites.map((item) => (
            <div key={item}>{item}</div>
          ))}
        </div>
      </section>

      <section className="rounded-2xl border border-gray-200 bg-gray-50 p-4 dark:border-gray-800 dark:bg-gray-900">
        <div className="font-semibold text-gray-900 dark:text-white">
          Estados de tarea
        </div>
        <div className="mt-3 space-y-2 text-gray-600 dark:text-gray-300">
          {estados.map(([title, description]) => (
            <div key={title}>
              <div className="font-medium text-gray-900 dark:text-white">{title}</div>
              <div>{description}</div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
};

export default FeaturePanel;

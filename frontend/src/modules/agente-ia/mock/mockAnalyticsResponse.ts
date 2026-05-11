import type { IADevChatResponse } from "@/services/ia-dev.service";

export const mockAnalyticsResponse: IADevChatResponse = {
  session_id: "mock-analytics-session",
  reply:
    "Se identificaron 500 materiales criticos en operacion_hfc. El saldo bajo se concentra en conectores, drop y grapas de anclaje, con mayor exposicion en tres moviles.",
  response_envelope: {
    mode: "user",
    progress_source: "backend",
    route: {
      channel: "mock",
      renderer: "split_dashboard",
    },
    fallback_used: {
      used: false,
      reason: "",
      flow: "",
    },
    legacy_used: false,
    contract_policy_applied: {
      version: "mock-v1",
    },
    needs_clarification: false,
    block_reason: "",
  },
  orchestrator: {
    intent: "analytics_query",
    domain: "inventario_logistica",
    selected_agent: "inventory_analyst",
    classifier_source: "mock",
    needs_database: true,
    output_mode: "dashboard",
    used_tools: ["query_execution_planner", "business_response_composer"],
  },
  data: {
    kpis: {
      materiales_criticos: 500,
      moviles_afectados: 23,
      saldo_total: 1842,
      cobertura_promedio_dias: 2.7,
    },
    insights: [
      "TIRAN224 concentra la mayor cantidad de materiales con cobertura menor a 3 dias.",
      "Los codigos DROP-11 y GRAPA-08 explican la mayor parte del riesgo operativo observado.",
      "La exposicion esta distribuida en 23 moviles, pero el 41% del saldo critico vive en tres cuadrillas.",
    ],
    table: {
      columns: [
        "movil",
        "cedula",
        "empleado",
        "codigo",
        "descripcion",
        "saldo_actual",
        "umbral_3_dias",
      ],
      rows: [
        {
          movil: "TIRAN224",
          cedula: "10203040",
          empleado: "Carlos Pardo",
          codigo: "DROP-11",
          descripcion: "Drop fibra 11 m",
          saldo_actual: 12,
          umbral_3_dias: 19,
        },
        {
          movil: "TIRAN224",
          cedula: "11223344",
          empleado: "Andrea Ruiz",
          codigo: "GRAPA-08",
          descripcion: "Grapa de anclaje",
          saldo_actual: 8,
          umbral_3_dias: 14,
        },
        {
          movil: "TIRAN314",
          cedula: "99887766",
          empleado: "Luis Mendoza",
          codigo: "CONEC-02",
          descripcion: "Conector rapido",
          saldo_actual: 15,
          umbral_3_dias: 21,
        },
      ],
      rowcount: 500,
    },
    extra_tables: [
      {
        columns: ["codigo", "descripcion", "moviles_afectados", "saldo_total"],
        rows: [
          {
            codigo: "DROP-11",
            descripcion: "Drop fibra 11 m",
            moviles_afectados: 12,
            saldo_total: 212,
          },
          {
            codigo: "GRAPA-08",
            descripcion: "Grapa de anclaje",
            moviles_afectados: 9,
            saldo_total: 147,
          },
          {
            codigo: "CONEC-02",
            descripcion: "Conector rapido",
            moviles_afectados: 8,
            saldo_total: 133,
          },
        ],
        rowcount: 32,
      },
    ],
    charts: [
      {
        engine: "amcharts5",
        chart_library: "amcharts5",
        type: "bar",
        title: "Top moviles por saldo critico",
        x_key: "movil",
        series: [{ name: "saldo_critico", value_key: "saldo_critico" }],
        data: [
          { movil: "TIRAN224", saldo_critico: 212 },
          { movil: "TIRAN102", saldo_critico: 173 },
          { movil: "TIRAN314", saldo_critico: 161 },
          { movil: "TIRAN089", saldo_critico: 128 },
        ],
      },
      {
        engine: "amcharts5",
        chart_library: "amcharts5",
        type: "line",
        title: "Cobertura promedio por cuadrilla",
        x_key: "semana",
        series: [{ name: "dias_cobertura", value_key: "dias_cobertura" }],
        data: [
          { semana: "S1", dias_cobertura: 4.2 },
          { semana: "S2", dias_cobertura: 3.6 },
          { semana: "S3", dias_cobertura: 3.1 },
          { semana: "S4", dias_cobertura: 2.7 },
        ],
      },
    ],
    series: [],
    labels: [],
    meta: {
      scope_label: "Demo operativa",
      generated_from: "mock_api",
    },
  },
  actions: [],
  memory_candidates: [],
  pending_proposals: [],
  working_updates: [],
  reasoning: {
    enabled: false,
    status: "done",
  },
  trace: [],
  memory: {
    used_messages: 2,
    capacity_messages: 40,
    usage_ratio: 0.05,
    trim_events: 0,
    saturated: false,
  },
};

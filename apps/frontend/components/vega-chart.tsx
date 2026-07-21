"use client";

import { useEffect, useRef, useState, useMemo } from "react";
import vegaEmbed from "vega-embed";
import { AlertCircle, Table2, Loader2 } from "lucide-react";

const MANGLAR_CHART_CONFIG = {
  background: "transparent",
  range: {
    category: ["#1b3f92", "#6fbb79", "#559bc5", "#69bba6", "#68bdbc"],
    ramp: ["#1b3f92", "#559bc5", "#68bdbc", "#69bba6", "#6fbb79"],
    diverging: ["#c81e3a", "#f4f7fb", "#1b3f92"],
  },
  axis: {
    labelColor: "#55637a",
    titleColor: "#55637a",
    labelFontSize: 12,
    gridColor: "#dde5ef",
    domainColor: "#dde5ef",
    tickColor: "#dde5ef",
  },
  legend: { labelColor: "#55637a", titleColor: "#55637a", labelFontSize: 12 },
  view: { stroke: null },
} as const;

export function VegaChart({ spec }: { spec: Record<string, unknown> }) {
  const ref = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!ref.current) return;
    setError(null);
    setLoading(true);

    const brandedSpec = {
      ...spec,
      config: { ...MANGLAR_CHART_CONFIG, ...((spec.config as object) ?? {}) },
    };
    const result = vegaEmbed(ref.current, brandedSpec as never, {
      actions: false,
      renderer: "svg",
    });

    result
      .then(() => setLoading(false))
      .catch((err: unknown) => {
        const message =
          err instanceof Error ? err.message : "Error al renderizar el gráfico";
        setError(message);
        setLoading(false);
      });

    return () => {
      result.then((r) => r.finalize()).catch(() => {});
    };
  }, [spec]);

  const dataValues = useMemo(() => extractDataForTable(spec), [spec]);

  return (
    <div className="mt-3 rounded-xl border border-border/60 bg-card p-4 shadow-sm">
      {error ? (
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Table2 className="h-4 w-4" />
            <span className="font-medium">Datos (vista de tabla)</span>
          </div>
          {dataValues.length > 0 ? (
            <div className="overflow-x-auto rounded-lg border border-border/40">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-border/40 bg-muted/50">
                    {Object.keys(dataValues[0] ?? {}).map((key) => (
                      <th
                        key={key}
                        className="px-3 py-2 text-left font-semibold text-foreground"
                      >
                        {key}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {dataValues.slice(0, 50).map((row, i) => (
                    <tr
                      key={i}
                      className="border-b border-border/20 last:border-0"
                    >
                      {Object.values(row).map((val, j) => (
                        <td key={j} className="px-3 py-1.5 text-muted-foreground">
                          {String(val ?? "")}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
              {dataValues.length > 50 && (
                <p className="px-3 py-2 text-xs text-muted-foreground">
                  Mostrando 50 de {dataValues.length} filas
                </p>
              )}
            </div>
          ) : (
            <div className="flex items-center gap-2 rounded-lg bg-destructive/10 border border-destructive/20 px-3 py-2.5 text-sm text-destructive">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}
        </div>
      ) : (
        <div className="w-full overflow-x-auto">
          {loading && (
            <div className="flex items-center gap-2 py-6 text-xs text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>Renderizando gráfico…</span>
            </div>
          )}
          <div ref={ref} className={loading ? "hidden" : "w-full overflow-x-auto"} />
        </div>
      )}
    </div>
  );
}

function extractDataForTable(spec: Record<string, unknown>): Record<string, unknown>[] {
  const data = spec.data as Record<string, unknown> | undefined;
  if (!data) return [];
  const values = data.values as Record<string, unknown>[] | undefined;
  if (Array.isArray(values)) return values;
  return [];
}

"use client";

import { useEffect, useRef } from "react";
import vegaEmbed from "vega-embed";

export function VegaChart({ spec }: { spec: Record<string, unknown> }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const result = vegaEmbed(ref.current, spec, { actions: false });
    return () => {
      result.then((r) => r.finalize()).catch(() => {});
    };
  }, [spec]);
  return <div ref={ref} className="mt-3 w-full overflow-x-auto" />;
}

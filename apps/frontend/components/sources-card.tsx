"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import type { Source } from "@/lib/api";
import { extractDatasetId, soqlPermalink } from "@/lib/api";
import { ExternalLink, Database, ChevronDown, ChevronRight, Code2 } from "lucide-react";

export function SourcesCard({ sources }: { sources: Source[] }) {
  if (!sources || sources.length === 0) return null;
  return (
    <div className="mt-4">
      <p className="mb-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        Fuentes consultadas
      </p>
      <div className="space-y-2.5">
        {sources.map((s, i) => (
          <SourceItem key={i} source={s} index={i} />
        ))}
      </div>
    </div>
  );
}

function SourceItem({ source, index }: { source: Source; index: number }) {
  const [soqlOpen, setSoqlOpen] = useState(false);
  const datasetId = extractDatasetId(source.permalink);

  return (
    <Card className="border-colombia-blue/15 bg-colombia-blue/[0.03] shadow-sm">
      <CardHeader className="flex flex-row items-center gap-2.5 pb-2 px-4 pt-3">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-colombia-blue/10">
          <Database className="h-3.5 w-3.5 text-colombia-blue" />
        </div>
        <div className="flex-1 min-w-0">
          <CardTitle className="text-sm font-semibold leading-tight text-foreground">
            {source.name || `Fuente ${index + 1}`}
          </CardTitle>
          {datasetId && (
            <p className="text-[10px] font-mono text-muted-foreground mt-0.5 truncate">
              {datasetId}
            </p>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-2.5 px-4 pb-3 pt-0">
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline" size="sm" className="h-7 text-xs border-colombia-blue/20 hover:bg-colombia-blue/10 hover:text-colombia-blue">
            <a href={source.permalink} target="_blank" rel="noopener noreferrer">
              <ExternalLink className="mr-1 h-3 w-3" />
              Ver dataset
            </a>
          </Button>
          {source.soql && (
            <Button asChild variant="secondary" size="sm" className="h-7 text-xs">
              <a
                href={soqlPermalink(datasetId, source.soql)}
                target="_blank"
                rel="noopener noreferrer"
              >
                Ver consulta
              </a>
            </Button>
          )}
          {source.soql && (
            <button
              type="button"
              onClick={() => setSoqlOpen(!soqlOpen)}
              className="inline-flex items-center gap-1 rounded-md border border-border bg-background px-2 py-1 text-xs text-muted-foreground hover:text-foreground hover:bg-muted transition-colors h-7"
            >
              <Code2 className="h-3 w-3" />
              SoQL
              {soqlOpen ? (
                <ChevronDown className="h-3 w-3" />
              ) : (
                <ChevronRight className="h-3 w-3" />
              )}
            </button>
          )}
        </div>
        {source.soql && soqlOpen && (
          <pre className="soql-code overflow-x-auto rounded-lg bg-gray-950 px-3 py-2.5 text-xs text-gray-200 leading-relaxed">
            {source.soql}
          </pre>
        )}
      </CardContent>
    </Card>
  );
}

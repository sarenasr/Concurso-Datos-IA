"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import type { Source } from "@/lib/api";
import { extractDatasetId, soqlPermalink } from "@/lib/api";
import { ExternalLink, Database } from "lucide-react";

export function SourcesCard({ sources }: { sources: Source[] }) {
  if (!sources || sources.length === 0) return null;
  return (
    <div className="mt-3">
      <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        Fuentes consultadas
      </p>
      <div className="space-y-2">
        {sources.map((s, i) => {
          const datasetId = extractDatasetId(s.permalink);
          return (
            <Card key={i} className="border-colombia-blue/20 bg-colombia-blue/5">
              <CardHeader className="flex flex-row items-center gap-2 pb-2">
                <Database className="h-4 w-4 text-colombia-blue" />
                <CardTitle className="text-sm font-semibold">{s.name}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="flex flex-wrap gap-2">
                  <Button asChild variant="outline" size="sm">
                    <a href={s.permalink} target="_blank" rel="noopener noreferrer">
                      <ExternalLink className="mr-1 h-3 w-3" />
                      Ver dataset
                    </a>
                  </Button>
                  {s.soql && (
                    <Button asChild variant="secondary" size="sm">
                      <a
                        href={soqlPermalink(datasetId, s.soql)}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        Ver consulta
                      </a>
                    </Button>
                  )}
                </div>
                {s.soql && (
                  <pre className="overflow-x-auto rounded-md bg-muted p-2 text-xs text-muted-foreground">
                    {s.soql}
                  </pre>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}

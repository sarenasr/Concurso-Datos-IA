"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import type { Citation } from "@/lib/api";
import { soqlPermalink } from "@/lib/api";

export function SourcesCard({ citations }: { citations: Citation[] }) {
  if (!citations || citations.length === 0) return null;
  return (
    <Card className="mt-3 border-accent/40">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-semibold">Fuentes</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {citations.map((c, i) => (
          <div key={i} className="rounded-md border p-2 text-sm">
            <div className="font-medium">{c.dataset}</div>
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <Button
                asChild
                variant="outline"
                size="sm"
              >
                <a href={c.permalink} target="_blank" rel="noopener noreferrer">
                  Ver dataset
                </a>
              </Button>
              <Button asChild variant="secondary" size="sm">
                <a
                  href={soqlPermalink(c.permalink.split("/d/").pop() || "", c.soql)}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Ver consulta (SoQL)
                </a>
              </Button>
            </div>
            {c.soql ? (
              <pre className="mt-2 overflow-x-auto rounded bg-muted p-2 text-xs">{c.soql}</pre>
            ) : null}
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

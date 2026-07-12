"use client";

import { Chat } from "@/components/chat";
import { Database } from "lucide-react";

export default function Home() {
  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-background">
      {/* Header */}
      <header className="flex shrink-0 items-center gap-3 border-b border-border/60 bg-background/95 backdrop-blur-sm px-4 py-3 md:px-6">
        {/* Logo: GovCo yellow circle with data icon */}
        <div className="flex h-11 w-11 items-center justify-center rounded-full bg-colombia-yellow shadow-md shadow-colombia-yellow/20">
          <Database className="h-5 w-5 text-accent-foreground" strokeWidth={2.25} />
        </div>
        <div className="flex flex-col">
          <h1 className="text-xl font-bold tracking-tight leading-tight text-foreground">
            DATIA
          </h1>
          <p className="text-[11px] text-muted-foreground leading-tight font-medium">
            Habla con los datos de Colombia
          </p>
        </div>
        {/* Colombian flag dots */}
        <div className="ml-auto hidden items-center gap-1.5 sm:flex">
          <span className="h-2.5 w-2.5 rounded-full bg-colombia-yellow" />
          <span className="h-2.5 w-2.5 rounded-full bg-colombia-blue" />
          <span className="h-2.5 w-2.5 rounded-full bg-colombia-red" />
        </div>
      </header>
      <Chat />
    </div>
  );
}

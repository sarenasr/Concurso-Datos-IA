"use client";

import { Chat } from "@/components/chat";
import Image from "next/image";

export default function Home() {
  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-background">
      {/* Header */}
      <header className="flex shrink-0 items-center gap-3 border-b border-border/60 bg-background/95 backdrop-blur-sm px-4 py-3 md:px-6">
        <Image src="/brand/manglar-isotipo.png" alt="Isotipo de Manglar" width={40} height={40} priority />
        <div>
          <h1 className="font-sans text-2xl font-extrabold tracking-display text-manglar-raiz dark:text-manglar-marea">
            Manglar
          </h1>
          <p className="text-sm text-muted-foreground">Habla con los datos de Colombia</p>
        </div>
        <div className="ml-auto flex items-center gap-1.5" aria-hidden="true">
          <span className="size-2 rounded-full bg-manglar-raiz" />
          <span className="size-2 rounded-full bg-manglar-rio" />
          <span className="size-2 rounded-full bg-manglar-marea" />
          <span className="size-2 rounded-full bg-manglar-brote" />
          <span className="size-2 rounded-full bg-manglar-copa" />
        </div>
      </header>
      <Chat />
    </div>
  );
}

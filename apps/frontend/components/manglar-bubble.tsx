"use client";

import { useState, useRef, useEffect } from "react";
import { Chat } from "@/components/chat";
import { MessageCircle, X } from "lucide-react";
import Image from "next/image";

export function ManglarBubble() {
  const [open, setOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="fixed bottom-6 right-6 z-50">
      {open && (
        <div
          ref={panelRef}
          className="manglar-panel-enter absolute bottom-20 right-0 flex w-[380px] flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-2xl shadow-black/25 sm:w-[420px]"
          style={
            {
              height: 520,
              "--background": "#ffffff",
              "--foreground": "#0a0a0a",
              "--card": "#ffffff",
              "--card-foreground": "#0a0a0a",
              "--muted": "#f5f5f5",
              "--muted-foreground": "#6b6b6b",
              "--border": "#e5e5e5",
              "--input": "#e5e5e5",
            } as React.CSSProperties
          }
        >
          <div className="flex shrink-0 items-center gap-3 border-b border-border/60 bg-primary px-4 py-3">
            <Image src="/brand/manglar-isotipo.png" alt="" width={28} height={28} />
            <div className="flex flex-1 flex-col">
              <span className="text-sm font-bold text-primary-foreground leading-tight">
                Manglar
              </span>
              <span className="text-[10px] text-primary-foreground/70 leading-tight font-medium">
                Habla con los datos
              </span>
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="flex h-8 w-8 items-center justify-center rounded-lg text-gray-600 transition-colors hover:bg-white/50 hover:text-gray-900"
              aria-label="Cerrar chat"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <Chat compact />
        </div>
      )}

      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={`manglar-bubble-pulse flex h-16 w-16 items-center justify-center rounded-full border-4 border-white transition-all duration-200 hover:scale-105 active:scale-95 ${
          open
            ? "manglar-bubble-idle bg-white shadow-lg shadow-black/20 text-primary"
            : "bg-primary text-primary-foreground"
        }`}
        aria-label={open ? "Cerrar chat Manglar" : "Abrir chat Manglar"}
      >
        {open ? (
          <X className="h-7 w-7" strokeWidth={2.5} />
        ) : (
          <MessageCircle className="h-7 w-7" strokeWidth={2.25} />
        )}
      </button>
    </div>
  );
}

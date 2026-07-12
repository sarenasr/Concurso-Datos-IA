"use client";

import { useState, useRef, useEffect } from "react";
import { Chat } from "@/components/chat";
import { MessageCircle, X, Database } from "lucide-react";

export function DatiaBubble() {
  const [open, setOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        return;
      }
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="fixed bottom-6 right-6 z-50">
      {open && (
        <div
          ref={panelRef}
          className="datia-panel-enter absolute bottom-16 right-0 flex w-[380px] flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-2xl shadow-black/20 sm:w-[400px]"
          style={{ height: 500 }}
        >
          <div className="flex shrink-0 items-center gap-3 border-b border-border bg-colombia-blue px-4 py-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-colombia-yellow shadow-sm">
              <Database className="h-4 w-4 text-accent-foreground" strokeWidth={2.25} />
            </div>
            <div className="flex flex-1 flex-col">
              <span className="text-sm font-bold text-white leading-tight">DATIA</span>
              <span className="text-[10px] text-white/70 leading-tight font-medium">
                Habla con los datos
              </span>
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="flex h-8 w-8 items-center justify-center rounded-lg text-white/70 transition-colors hover:bg-white/10 hover:text-white"
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
        className={`datia-bubble-pulse flex h-14 w-14 items-center justify-center rounded-full bg-colombia-yellow text-accent-foreground shadow-lg shadow-colombia-yellow/30 transition-all duration-200 hover:scale-105 hover:shadow-xl hover:shadow-colombia-yellow/40 active:scale-95 ${
          open ? "datia-bubble-idle" : ""
        }`}
        aria-label={open ? "Cerrar chat DATIA" : "Abrir chat DATIA"}
      >
        {open ? (
          <X className="h-6 w-6" strokeWidth={2.25} />
        ) : (
          <MessageCircle className="h-6 w-6" strokeWidth={2.25} />
        )}
      </button>
    </div>
  );
}

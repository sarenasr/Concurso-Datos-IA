"use client";

import { useState, useRef, useEffect } from "react";
import { Chat } from "@/components/chat";
import { X } from "lucide-react";

export function ManglarBubble() {
  const [open, setOpen] = useState(false);
  const [showWelcome, setShowWelcome] = useState(true);
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

  // Auto-dismiss the welcome speech-bubble after 6s on first mount.
  useEffect(() => {
    if (!showWelcome) return;
    const t = setTimeout(() => setShowWelcome(false), 6000);
    return () => clearTimeout(t);
  }, [showWelcome]);

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
          <div className="flex shrink-0 items-center gap-3 border-b border-white/10 bg-manglar-raiz px-4 py-3">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/brand/manglar-isotipo.png"
              alt=""
              width={28}
              height={28}
              style={{ filter: "invert(1)" }}
              className="shrink-0"
            />
            <div className="flex flex-1 flex-col">
              <span className="text-sm font-bold leading-tight text-white">
                Manglar
              </span>
              <span className="text-[10px] font-medium leading-tight text-white/70">
                Habla con los datos
              </span>
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="flex h-8 w-8 items-center justify-center rounded-lg text-white/70 transition-colors hover:bg-white/15 hover:text-white"
              aria-label="Cerrar chat"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <Chat compact />
        </div>
      )}

      {!open && showWelcome && (
        <div
          className="manglar-panel-enter pointer-events-none absolute bottom-[4.5rem] right-0 flex w-[260px] items-center gap-2 rounded-2xl border border-border/60 bg-card px-3 py-2.5 shadow-lg shadow-black/10"
          role="status"
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/brand/manglar-isotipo.png"
            alt=""
            width={28}
            height={28}
            className="shrink-0"
          />
          <div className="min-w-0 flex-1 text-xs">
            <p className="font-semibold text-foreground leading-tight">
              Hola, soy Manglar
            </p>
            <p className="text-muted-foreground leading-tight">
              Pregúntame sobre los datos de Colombia.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setShowWelcome(false)}
            className="pointer-events-auto -mr-1 flex h-6 w-6 shrink-0 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            aria-label="Cerrar aviso"
          >
            <X className="h-3 w-3" />
          </button>
        </div>
      )}

      <button
        type="button"
        onClick={() => {
          setShowWelcome(false);
          setOpen((v) => !v);
        }}
        className={`manglar-bubble-pulse flex h-16 w-16 items-center justify-center rounded-full border-4 border-white transition-all duration-200 hover:scale-105 active:scale-95 ${
          open
            ? "manglar-bubble-idle bg-white shadow-lg shadow-black/20 text-manglar-raiz"
            : "bg-manglar-raiz text-white"
        }`}
        aria-label={open ? "Cerrar chat Manglar" : "Abrir chat Manglar"}
      >
        {open ? (
          <X className="h-7 w-7" strokeWidth={2.5} />
        ) : (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src="/brand/manglar-isotipo.png"
            alt="Manglar"
            width={34}
            height={34}
            style={{ filter: "invert(1)" }}
          />
        )}
      </button>
    </div>
  );
}
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
          className="manglar-panel-enter absolute bottom-28 right-0 flex w-[min(440px,calc(100vw-3rem))] flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-2xl shadow-black/25"
          style={
            {
              height: "min(560px, calc(100vh - 9rem))",
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
            <span className="flex h-16 w-16 shrink-0 items-center justify-center rounded-full bg-white shadow-sm">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src="/brand/manglar-isotipo.png"
                alt=""
                width={48}
                height={48}
              />
            </span>
            <div className="flex flex-1 flex-col">
              <span className="text-sm font-bold leading-tight text-white">
                Manglar
              </span>
              <span className="text-[10px] font-medium leading-tight text-white/70">
                Explora Colombia conversando
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

      {/* Welcome message - desktop only, positioned to the left of bubble */}
      {!open && showWelcome && (
        <div
          className="manglar-panel-enter pointer-events-none hidden md:block absolute bottom-8 right-[100px] w-[340px] rounded-2xl border border-border/60 bg-card px-4 py-3 pr-8 shadow-lg shadow-black/10"
          role="status"
        >
          <button
            type="button"
            onClick={() => setShowWelcome(false)}
            className="pointer-events-auto absolute top-2 right-2 flex h-6 w-6 shrink-0 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            aria-label="Cerrar aviso"
          >
            <X className="h-3 w-3" />
          </button>
          <div className="flex items-center gap-3">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/brand/manglar-isotipo.png"
              alt=""
              width={40}
              height={40}
              className="shrink-0"
            />
            <div className="min-w-0 flex-1 text-sm">
              <p className="font-semibold text-foreground leading-tight">
                Explora Colombia conversando
              </p>
              <p className="text-muted-foreground leading-tight">
                Pregúntame sobre los datos de Colombia.
              </p>
            </div>
          </div>
        </div>
      )}

      <button
        type="button"
        onClick={() => {
          setShowWelcome(false);
          setOpen((v) => !v);
        }}
        className={`manglar-bubble-pulse flex items-center justify-center rounded-full border border-border bg-white text-manglar-raiz shadow-lg shadow-black/20 transition-all duration-200 hover:scale-105 active:scale-95 ${
          open ? "manglar-bubble-idle" : ""
        } md:h-24 md:w-24 h-20 w-20`}
        aria-label={open ? "Cerrar chat Manglar" : "Abrir chat Manglar"}
      >
        {open ? (
          <X className="md:h-9 md:w-9 h-8 w-8" strokeWidth={2.5} />
        ) : (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src="/brand/manglar-isotipo.png"
            alt="Manglar"
            width={64}
            height={64}
            className="md:w-[64px] md:h-[64px] w-[56px] h-[56px]"
          />
        )}
      </button>
    </div>
  );
}
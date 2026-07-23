"use client";

import { Chat } from "@/components/chat";
import { useTheme } from "next-themes";
import { Sun, Moon } from "lucide-react";
import { useEffect, useState } from "react";

export default function Home() {
  const { theme, setTheme, resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setMounted(true), 0);
    return () => clearTimeout(timer);
  }, []);

  if (!mounted) {
    return (
      <div className="flex h-dvh flex-col overflow-hidden bg-background">
        <header className="flex shrink-0 items-center gap-4 border-b border-border/60 bg-background/95 backdrop-blur-sm px-4 py-3 md:px-6">
          <img src="/brand/manglar-isotipo.png" alt="Isotipo de Manglar" width={56} height={56} className="shrink-0" />
        </header>
        <Chat />
      </div>
    );
  }

  const currentTheme = resolvedTheme || theme;

  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-background">
      {/* Header - isotype on left, theme toggle on right */}
      <header className="flex shrink-0 items-center justify-between gap-4 border-b border-border/60 bg-background/95 backdrop-blur-sm px-4 py-3 md:px-6">
        {/* Isotype on the left */}
        <img
          src="/brand/manglar-isotipo.png"
          alt="Isotipo de Manglar"
          width={56}
          height={56}
          className="shrink-0"
        />
        {/* Theme toggle on the right */}
        <button
          onClick={() => setTheme(currentTheme === "dark" ? "light" : "dark")}
          className="flex h-10 w-10 items-center justify-center rounded-lg bg-muted/50 text-foreground hover:bg-muted transition-colors"
          aria-label={currentTheme === "dark" ? "Cambiar a modo claro" : "Cambiar a modo oscuro"}
        >
          {currentTheme === "dark" ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
        </button>
      </header>
      <Chat />
    </div>
  );
}

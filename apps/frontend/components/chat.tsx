"use client";

import { useState, useRef, useEffect, useCallback, memo, useMemo } from "react";
import ReactMarkdown from "react-markdown";
import dynamic from "next/dynamic";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { SourcesCard } from "@/components/sources-card";
import { streamChat, type Source, type ChatEvent } from "@/lib/api";
import {
  Send,
  ChevronDown,
  ChevronRight,
  Code2,
  Sparkles,
  User,
  AlertCircle,
} from "lucide-react";
import { LoadingLogo } from "@/components/loading-logo";

const VegaChart = dynamic(
  () => import("@/components/vega-chart").then((m) => m.VegaChart),
  {
    ssr: false,
    loading: () => (
      <p className="mt-3 text-xs text-muted-foreground">Cargando gráfico…</p>
    ),
  }
);

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

type UserMsg = {
  id: string;
  role: "user";
  content: string;
};

type AssistantMsg = {
  id: string;
  role: "assistant";
  thinking: string;
  query: string;
  dataset: string;
  answer: string;
  chart: Record<string, unknown> | null;
  sources: Source[];
  streaming: boolean;
  error: string | null;
};

type Message = UserMsg | AssistantMsg;

function emptyAssistant(id: string): AssistantMsg {
  return {
    id,
    role: "assistant",
    thinking: "",
    query: "",
    dataset: "",
    answer: "",
    chart: null,
    sources: [],
    streaming: true,
    error: null,
  };
}

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const EXAMPLES = [
  "¿Cuántos contratos firmó Medellín en 2025?",
  "¿Qué datos hay sobre vacunación?",
  "¿Cuál fue la TRM del último mes?",
];

/* ------------------------------------------------------------------ */
/*  SoQL Block                                                         */
/* ------------------------------------------------------------------ */

const SoQLBlock = memo(function SoQLBlock({
  query,
  dataset,
}: {
  query: string;
  dataset: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-3 rounded-lg border border-border/50 overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 bg-gray-900 px-3 py-2.5 text-left text-xs font-medium text-gray-300 hover:text-white transition-colors"
      >
        <Code2 className="h-3.5 w-3.5 text-manglar-marea shrink-0" />
        <span className="text-gray-400">Consulta SoQL</span>
        {dataset && (
          <span className="rounded bg-manglar-marea/15 px-1.5 py-0.5 text-manglar-marea font-mono text-[10px] border border-manglar-marea/20">
            {dataset}
          </span>
        )}
        <span className="ml-auto shrink-0">
          {open ? (
            <ChevronDown className="h-3.5 w-3.5" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5" />
          )}
        </span>
      </button>
      {open && (
        <pre className="soql-code overflow-x-auto bg-gray-950 px-3 py-3 text-xs text-gray-200 leading-relaxed border-t border-gray-800">
          {query}
        </pre>
      )}
    </div>
  );
});

/* ------------------------------------------------------------------ */
/*  Assistant Bubble                                                   */
/* ------------------------------------------------------------------ */

const AssistantBubble = memo(function AssistantBubble({
  msg,
}: {
  msg: AssistantMsg;
}) {
  const hasContent =
    msg.thinking ||
    msg.query ||
    msg.answer ||
    msg.chart ||
    msg.sources.length > 0 ||
    msg.error;

  const renderedAnswer = useMemo(
    () => <ReactMarkdown>{msg.answer}</ReactMarkdown>,
    [msg.answer]
  );

  return (
    <div className="space-y-1">
      {msg.thinking && (
        <p className="text-sm italic text-muted-foreground">
          <Sparkles className="mr-1 inline h-3 w-3 text-manglar-marea" />
          {msg.thinking}
        </p>
      )}

      {msg.streaming && !msg.answer && (
        <div className="flex flex-col items-center py-2">
          <LoadingLogo size={48} />
        </div>
      )}

      {msg.query && <SoQLBlock query={msg.query} dataset={msg.dataset} />}

      {msg.answer && (
        <div className="prose prose-sm mt-2 max-w-none dark:prose-invert prose-p:leading-relaxed prose-pre:bg-muted prose-pre:text-foreground prose-headings:text-foreground prose-a:text-primary">
          {renderedAnswer}
        </div>
      )}

      {msg.chart && <VegaChart spec={msg.chart} />}

      {msg.sources.length > 0 && <SourcesCard sources={msg.sources} />}

      {msg.error && (
        <div className="flex items-start gap-2 rounded-lg bg-destructive/10 border border-destructive/20 px-3 py-2.5 text-sm text-destructive">
          <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
          <span>{msg.error}</span>
        </div>
      )}
    </div>
  );
});

/* ------------------------------------------------------------------ */
/*  Chat Component                                                     */
/* ------------------------------------------------------------------ */

export function Chat({ compact = false }: { compact?: boolean } = {}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const scrollerRef = useRef<HTMLDivElement>(null);
  const isPinnedRef = useRef(true);
  const idRef = useRef(0);

  const nextId = useCallback(() => `${++idRef.current}`, []);

  const onScroll = useCallback(() => {
    const el = scrollerRef.current;
    if (!el) return;
    isPinnedRef.current =
      el.scrollHeight - el.scrollTop - el.clientHeight < 80;
  }, []);

  useEffect(() => {
    if (!isPinnedRef.current) return;
    sentinelRef.current?.scrollIntoView({ behavior: "auto" });
  }, [messages]);

  useEffect(() => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
    }
  }, [input]);

  function extractAssistantText(msg: AssistantMsg): string {
    return msg.answer || msg.thinking || "";
  }

  const send = useCallback(
    async (text?: string) => {
      const content = (text ?? input).trim();
      if (!content || loading) return;

      if (abortRef.current) abortRef.current.abort();

      const userMsg: UserMsg = { id: nextId(), role: "user", content };
      const assistantMsg: AssistantMsg = emptyAssistant(nextId());

      const history = [...messages, userMsg];
      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      setInput("");
      setLoading(true);

      const controller = new AbortController();
      abortRef.current = controller;

      const inputMessages = history.map((m) => ({
        role: m.role,
        content: m.role === "user" ? m.content : extractAssistantText(m),
      }));

      try {
        await streamChat(
          inputMessages,
          (event: ChatEvent) => {
            setMessages((prev) => {
              const idx = prev.findIndex(
                (m) => m.role === "assistant" && m.id === assistantMsg.id
              );
              if (idx < 0) return prev;
              const updated = { ...(prev[idx] as AssistantMsg) };
              switch (event.type) {
                case "thinking":
                  updated.thinking = event.content;
                  break;
                case "query":
                  updated.query = event.content;
                  updated.dataset = event.dataset;
                  break;
                case "answer":
                  updated.answer = event.content;
                  break;
                case "chart":
                  updated.chart = event.content;
                  break;
                case "sources":
                  updated.sources = event.content;
                  break;
              }
              const copy = [...prev];
              copy[idx] = updated;
              return copy;
            });
          },
          controller.signal
        );
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") {
          setMessages((prev) =>
            prev.map((m) =>
              m.role === "assistant" && m.id === assistantMsg.id
                ? { ...m, streaming: false }
                : m
            )
          );
          return;
        }

        const isNetworkError =
          err instanceof TypeError &&
          (err.message.includes("fetch") ||
            err.message.includes("network") ||
            err.message.includes("Failed"));

        const errorMessage = isNetworkError
          ? "No se pudo conectar con el servidor. ¿Está el backend funcionando?"
          : err instanceof Error
            ? err.message
            : "Error desconocido";

        setMessages((prev) => {
          const target = prev.find(
            (m) => m.role === "assistant" && m.id === assistantMsg.id
          );
          if (!target) return prev;
          return prev.map((m) =>
            m.role === "assistant" && m.id === assistantMsg.id
              ? { ...m, error: errorMessage }
              : m
          );
        });
      } finally {
        if (abortRef.current === controller) {
          setLoading(false);
        }
        setMessages((prev) =>
          prev.map((m) =>
            m.role === "assistant" && m.id === assistantMsg.id
              ? { ...m, streaming: false }
              : m
          )
        );
      }
    },
    [input, loading, messages, nextId]
  );

  function onKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  const isEmpty = messages.length === 0;

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div
        ref={scrollerRef}
        onScroll={onScroll}
        className="flex-1 overflow-y-auto chat-scroll"
      >
        <div
          className={
            compact
              ? "mx-auto w-full px-3 py-4"
              : "mx-auto w-full max-w-3xl px-4 py-6 pb-4"
          }
        >
          {isEmpty ? (
            <div
              className={
                compact
                  ? "flex flex-col items-center justify-center py-6 text-center"
                  : "flex flex-col items-center justify-center py-12 md:py-20 text-center"
              }
            >
              <div
                className={
                  compact
                    ? "mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-manglar-marea/15 ring-2 ring-manglar-marea/20"
                    : "mb-6 flex h-20 w-20 items-center justify-center rounded-full bg-manglar-marea/15 ring-2 ring-manglar-marea/20"
                }
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src="/brand/manglar-isotipo.png"
                  alt="Manglar"
                  width={compact ? 28 : 48}
                  height={compact ? 28 : 48}
                  className="shrink-0"
                />
              </div>
              <h2
                className={
                  compact
                    ? "mb-1 text-base font-bold tracking-tight text-foreground"
                    : "mb-2 text-2xl font-bold tracking-tight text-foreground md:text-3xl"
                }
              >
                ¿Qué quieres saber hoy?
              </h2>
              <p
                className={
                  compact
                    ? "mb-4 max-w-xs text-xs text-muted-foreground leading-relaxed"
                    : "mb-10 max-w-md text-sm text-muted-foreground leading-relaxed"
                }
              >
                Pregúntame sobre datos abiertos de Colombia. Busco en datos.gov.co,
                escribo la consulta y te doy la respuesta con fuentes.
              </p>
              <div
                className={
                  compact
                    ? "flex flex-wrap justify-center gap-1.5"
                    : "flex flex-wrap justify-center gap-2.5"
                }
              >
                {EXAMPLES.map((q) => (
                  <button
                    key={q}
                    type="button"
                    onClick={() => send(q)}
                    className={
                      compact
                        ? "rounded-full border border-border bg-card px-3 py-1.5 text-xs text-foreground shadow-sm transition-all duration-200 hover:border-manglar-marea hover:bg-manglar-marea/10 hover:shadow-md hover:shadow-manglar-marea/5 active:scale-[0.98]"
                        : "rounded-full border border-border bg-card px-4 py-2.5 text-sm text-foreground shadow-sm transition-all duration-200 hover:border-manglar-marea hover:bg-manglar-marea/10 hover:shadow-md hover:shadow-manglar-marea/5 active:scale-[0.98]"
                    }
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className={compact ? "space-y-4" : "space-y-6"}>
              {messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`flex gap-3 ${
                    msg.role === "user" ? "justify-end" : "justify-start"
                  }`}
                >
                  {msg.role === "assistant" && (
                    <Avatar className="mt-0.5 h-8 w-8 shrink-0 border-2 border-manglar-marea/30">
                      <AvatarImage src="/brand/manglar-isotipo.png" alt="Manglar" />
                      <AvatarFallback className="bg-muted text-muted-foreground font-bold text-xs">
                        M
                      </AvatarFallback>
                    </Avatar>
                  )}
                  {msg.role === "user" ? (
                    <div className="flex max-w-[85%] items-end gap-2">
                      <div className="rounded-2xl rounded-br-sm bg-primary px-4 py-2.5 text-sm text-primary-foreground shadow-sm">
                        {msg.content}
                      </div>
                      <Avatar className="h-8 w-8 shrink-0">
                        <AvatarFallback className="bg-muted text-muted-foreground">
                          <User className="h-4 w-4" />
                        </AvatarFallback>
                      </Avatar>
                    </div>
                  ) : (
                    <div className="min-w-0 flex-1 max-w-[85%]">
                      <AssistantBubble msg={msg} />
                    </div>
                  )}
                </div>
              ))}
              <div ref={sentinelRef} className="h-1" />
            </div>
          )}
        </div>
      </div>

      <div className="shrink-0 border-t border-border/60 bg-background/95">
        <div
          className={
            compact
              ? "mx-auto flex w-full items-end gap-2 px-3 py-2.5"
              : "mx-auto flex w-full max-w-3xl items-end gap-2 px-4 py-3"
          }
        >
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKey}
            placeholder="Pregunta sobre los datos de Colombia..."
            disabled={loading}
            rows={1}
            className="flex-1 resize-none rounded-xl border border-border bg-muted/50 px-4 py-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-manglar-marea/40 focus:border-manglar-marea/40 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
          />
          {loading ? (
            <Button
              onClick={() => abortRef.current?.abort()}
              size="icon"
              className="h-11 w-11 shrink-0 rounded-xl bg-destructive/10 text-destructive border border-destructive/30 shadow-sm hover:bg-destructive/20 transition-all"
              aria-label="Detener"
              title="Detener generación"
            >
              <span className="h-3.5 w-3.5 block rounded-sm bg-destructive" />
            </Button>
          ) : (
            <Button
              onClick={() => send()}
              disabled={!input.trim()}
              size="icon"
              className="h-11 w-11 shrink-0 rounded-xl bg-primary text-primary-foreground shadow-sm hover:bg-primary/90 disabled:opacity-40 transition-all"
              aria-label="Enviar"
            >
              <Send className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

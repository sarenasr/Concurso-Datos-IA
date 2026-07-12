"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { SourcesCard } from "@/components/sources-card";
import { VegaChart } from "@/components/vega-chart";
import { streamChat, type Source, type ChatEvent } from "@/lib/api";
import {
  Send,
  ChevronDown,
  ChevronRight,
  Code2,
  Loader2,
  Sparkles,
  User,
  MessageCircle,
  AlertCircle,
} from "lucide-react";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

type UserMsg = {
  role: "user";
  content: string;
};

type AssistantMsg = {
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

function emptyAssistant(): AssistantMsg {
  return {
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
/*  Thinking indicator                                                 */
/* ------------------------------------------------------------------ */

function ThinkingIndicator() {
  return (
    <div className="flex items-center gap-2.5 text-sm font-medium text-muted-foreground">
      <span>DATIA está pensando</span>
      <span className="flex gap-1">
        <span className="thinking-dot h-2 w-2 rounded-full bg-colombia-yellow" />
        <span className="thinking-dot h-2 w-2 rounded-full bg-colombia-yellow" />
        <span className="thinking-dot h-2 w-2 rounded-full bg-colombia-yellow" />
      </span>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  SoQL Block                                                         */
/* ------------------------------------------------------------------ */

function SoQLBlock({ query, dataset }: { query: string; dataset: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-3 rounded-lg border border-border/50 overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 bg-gray-900 px-3 py-2.5 text-left text-xs font-medium text-gray-300 hover:text-white transition-colors"
      >
        <Code2 className="h-3.5 w-3.5 text-colombia-yellow shrink-0" />
        <span className="text-gray-400">Consulta SoQL</span>
        {dataset && (
          <span className="rounded bg-colombia-yellow/15 px-1.5 py-0.5 text-colombia-yellow font-mono text-[10px] border border-colombia-yellow/20">
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
}

/* ------------------------------------------------------------------ */
/*  Assistant Bubble                                                   */
/* ------------------------------------------------------------------ */

function AssistantBubble({ msg }: { msg: AssistantMsg }) {
  const hasContent =
    msg.thinking ||
    msg.query ||
    msg.answer ||
    msg.chart ||
    msg.sources.length > 0 ||
    msg.error;

  return (
    <div className="space-y-1">
      {/* Thinking text */}
      {msg.thinking && (
        <p className="text-sm italic text-muted-foreground">
          <Sparkles className="mr-1 inline h-3 w-3 text-colombia-yellow" />
          {msg.thinking}
        </p>
      )}

      {/* Thinking indicator when streaming with no content yet */}
      {msg.streaming && !msg.answer && !hasContent && <ThinkingIndicator />}

      {/* SoQL query block */}
      {msg.query && <SoQLBlock query={msg.query} dataset={msg.dataset} />}

      {/* Answer */}
      {msg.answer && (
        <div className="prose prose-sm mt-2 max-w-none dark:prose-invert prose-p:leading-relaxed prose-pre:bg-muted prose-pre:text-foreground prose-headings:text-foreground prose-a:text-colombia-blue">
          <ReactMarkdown>{msg.answer}</ReactMarkdown>
        </div>
      )}

      {/* Chart */}
      {msg.chart && <VegaChart spec={msg.chart} />}

      {/* Sources */}
      {msg.sources.length > 0 && <SourcesCard sources={msg.sources} />}

      {/* Error */}
      {msg.error && (
        <div className="flex items-start gap-2 rounded-lg bg-destructive/10 border border-destructive/20 px-3 py-2.5 text-sm text-destructive">
          <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
          <span>{msg.error}</span>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Chat Component                                                     */
/* ------------------------------------------------------------------ */

export function Chat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    sentinelRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Auto-resize textarea
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

      const userMsg: UserMsg = { role: "user", content };
      const assistantMsg: AssistantMsg = emptyAssistant();

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
              const copy = [...prev];
              const last = copy[copy.length - 1];
              if (!last || last.role !== "assistant") return prev;
              const updated = { ...last };
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
              copy[copy.length - 1] = updated;
              return copy;
            });
          },
          controller.signal
        );
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") return;

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
          const copy = [...prev];
          const last = copy[copy.length - 1];
          if (last && last.role === "assistant") {
            copy[copy.length - 1] = {
              ...last,
              error: errorMessage,
            };
          }
          return copy;
        });
      } finally {
        setMessages((prev) => {
          const copy = [...prev];
          const last = copy[copy.length - 1];
          if (last && last.role === "assistant") {
            copy[copy.length - 1] = { ...last, streaming: false };
          }
          return copy;
        });
        setLoading(false);
      }
    },
    [input, loading, messages]
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
      {/* Messages area */}
      <div className="flex-1 overflow-y-auto chat-scroll">
        <div className="mx-auto w-full max-w-3xl px-4 py-6 pb-4">
          {isEmpty ? (
            /* ---- Empty state ---- */
            <div className="flex flex-col items-center justify-center py-12 md:py-20 text-center">
              <div className="mb-6 flex h-20 w-20 items-center justify-center rounded-full bg-colombia-yellow/15 ring-2 ring-colombia-yellow/20">
                <MessageCircle className="h-10 w-10 text-colombia-yellow" strokeWidth={1.75} />
              </div>
              <h2 className="mb-2 text-2xl font-bold tracking-tight text-foreground md:text-3xl">
                ¿Qué quieres saber hoy?
              </h2>
              <p className="mb-10 max-w-md text-sm text-muted-foreground leading-relaxed">
                Pregúntame sobre datos abiertos de Colombia. Busco en datos.gov.co,
                escribo la consulta y te doy la respuesta con fuentes.
              </p>
              <div className="flex flex-wrap justify-center gap-2.5">
                {EXAMPLES.map((q) => (
                  <button
                    key={q}
                    type="button"
                    onClick={() => send(q)}
                    className="rounded-full border border-border bg-card px-4 py-2.5 text-sm text-foreground shadow-sm transition-all duration-200 hover:border-colombia-yellow hover:bg-colombia-yellow/10 hover:shadow-md hover:shadow-colombia-yellow/5 active:scale-[0.98]"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            /* ---- Messages ---- */
            <div className="space-y-6">
              {messages.map((msg, i) => (
                <div
                  key={i}
                  className={`flex gap-3 ${
                    msg.role === "user" ? "justify-end" : "justify-start"
                  }`}
                >
                  {msg.role === "assistant" && (
                    <Avatar className="mt-0.5 h-8 w-8 shrink-0 border-2 border-colombia-yellow/30">
                      <AvatarFallback className="bg-colombia-yellow/15 text-colombia-yellow font-bold text-xs">
                        DA
                      </AvatarFallback>
                    </Avatar>
                  )}
                  {msg.role === "user" ? (
                    <div className="flex max-w-[85%] items-end gap-2">
                      <div className="rounded-2xl rounded-br-sm bg-colombia-blue px-4 py-2.5 text-sm text-white shadow-sm">
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

      {/* ---- Input area (fixed bottom) ---- */}
      <div className="shrink-0 border-t border-border/60 bg-background/95 backdrop-blur-sm">
        <div className="mx-auto flex w-full max-w-3xl items-end gap-2 px-4 py-3">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKey}
            placeholder="Pregunta sobre los datos de Colombia..."
            disabled={loading}
            rows={1}
            className="flex-1 resize-none rounded-xl border border-border bg-muted/50 px-4 py-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-colombia-yellow/40 focus:border-colombia-yellow/40 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
          />
          <Button
            onClick={() => send()}
            disabled={loading || !input.trim()}
            size="icon"
            className="h-11 w-11 shrink-0 rounded-xl bg-colombia-yellow text-accent-foreground shadow-sm hover:bg-colombia-yellow/90 disabled:opacity-40 transition-all"
          >
            {loading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}

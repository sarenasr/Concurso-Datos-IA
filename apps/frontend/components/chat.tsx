"use client";

import { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { ScrollArea } from "@/components/ui/scroll-area";
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
} from "lucide-react";

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

const EXAMPLES = [
  "¿Cuántos contratos firmó Medellín en 2025?",
  "¿Qué datos hay sobre vacunación?",
  "¿Cuál fue la TRM del último mes?",
];

function ThinkingIndicator() {
  return (
    <div className="flex items-center gap-2 text-sm text-muted-foreground">
      <Loader2 className="h-4 w-4 animate-spin text-accent" />
      <span>Analizando datos</span>
      <span className="flex gap-0.5">
        <span className="thinking-dot h-1.5 w-1.5 rounded-full bg-muted-foreground" />
        <span className="thinking-dot h-1.5 w-1.5 rounded-full bg-muted-foreground" />
        <span className="thinking-dot h-1.5 w-1.5 rounded-full bg-muted-foreground" />
      </span>
    </div>
  );
}

function SoQLBlock({ query, dataset }: { query: string; dataset: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-2 rounded-lg border bg-muted/50">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
      >
        <Code2 className="h-3.5 w-3.5" />
        <span>Consulta SoQL</span>
        {dataset && (
          <span className="rounded bg-colombia-blue/10 px-1.5 py-0.5 text-colombia-blue font-mono">
            {dataset}
          </span>
        )}
        <span className="ml-auto">
          {open ? (
            <ChevronDown className="h-3.5 w-3.5" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5" />
          )}
        </span>
      </button>
      {open && (
        <pre className="overflow-x-auto border-t px-3 py-2 text-xs font-mono text-foreground">
          {query}
        </pre>
      )}
    </div>
  );
}

function AssistantBubble({ msg }: { msg: AssistantMsg }) {
  const hasContent =
    msg.thinking || msg.query || msg.answer || msg.chart || msg.sources.length > 0 || msg.error;

  return (
    <div className="space-y-1">
      {msg.thinking && (
        <p className="text-sm italic text-muted-foreground">
          <Sparkles className="mr-1 inline h-3 w-3 text-accent" />
          {msg.thinking}
        </p>
      )}

      {msg.streaming && !msg.answer && !hasContent && <ThinkingIndicator />}

      {msg.query && <SoQLBlock query={msg.query} dataset={msg.dataset} />}

      {msg.answer && (
        <div className="prose prose-sm mt-1 max-w-none dark:prose-invert prose-p:leading-relaxed prose-pre:bg-muted prose-pre:text-foreground">
          <ReactMarkdown>{msg.answer}</ReactMarkdown>
        </div>
      )}

      {msg.chart && <VegaChart spec={msg.chart} />}

      {msg.sources.length > 0 && <SourcesCard sources={msg.sources} />}

      {msg.error && (
        <p className="text-sm text-destructive">{msg.error}</p>
      )}
    </div>
  );
}

export function Chat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    sentinelRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function send(text?: string) {
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
      setMessages((prev) => {
        const copy = [...prev];
        const last = copy[copy.length - 1];
        if (last && last.role === "assistant") {
          copy[copy.length - 1] = {
            ...last,
            error: err instanceof Error ? err.message : "Error desconocido",
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
  }

  function extractAssistantText(msg: AssistantMsg): string {
    return msg.answer || msg.thinking || "";
  }

  function onKey(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  const isEmpty = messages.length === 0;

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <ScrollArea className="flex-1">
        <div className="mx-auto max-w-3xl px-4 py-6">
          {isEmpty ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <div className="mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-accent/15">
                <Sparkles className="h-8 w-8 text-accent" />
              </div>
              <h2 className="mb-2 text-2xl font-semibold tracking-tight">
                ¿Qué quieres saber hoy?
              </h2>
              <p className="mb-8 max-w-md text-sm text-muted-foreground">
                Pregúntame sobre datos abiertos de Colombia. Busco en datos.gov.co,
                escribo la consulta y te doy la respuesta con fuentes.
              </p>
              <div className="flex flex-wrap justify-center gap-2">
                {EXAMPLES.map((q) => (
                  <button
                    key={q}
                    type="button"
                    onClick={() => send(q)}
                    className="rounded-full border bg-card px-4 py-2 text-sm text-foreground shadow-sm transition-colors hover:border-accent hover:bg-accent/10"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="space-y-6">
              {messages.map((msg, i) => (
                <div
                  key={i}
                  className={`flex gap-3 ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                >
                  {msg.role === "assistant" && (
                    <Avatar className="mt-0.5 h-8 w-8 shrink-0 border border-accent/30">
                      <AvatarFallback className="bg-accent/15 text-accent font-semibold text-xs">
                        DA
                      </AvatarFallback>
                    </Avatar>
                  )}
                  {msg.role === "user" ? (
                    <div className="flex max-w-[80%] items-center gap-2">
                      <div className="rounded-2xl rounded-br-sm bg-primary px-4 py-2.5 text-sm text-primary-foreground shadow-sm">
                        {msg.content}
                      </div>
                      <Avatar className="h-8 w-8 shrink-0">
                        <AvatarFallback className="bg-muted text-xs">
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
      </ScrollArea>

      <div className="border-t bg-background/80 backdrop-blur-sm">
        <div className="mx-auto flex max-w-3xl items-center gap-2 px-4 py-3">
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKey}
            placeholder="Pregunta sobre datos abiertos de Colombia…"
            disabled={loading}
            className="h-11 rounded-xl border-muted bg-muted/50 focus-visible:bg-background transition-colors"
          />
          <Button
            onClick={() => send()}
            disabled={loading || !input.trim()}
            size="icon"
            className="h-11 w-11 rounded-xl bg-accent text-accent-foreground shadow-sm hover:bg-accent/90"
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

"use client";

import { useState, useRef } from "react";
import ReactMarkdown from "react-markdown";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { ScrollArea } from "@/components/ui/scroll-area";
import { SourcesCard } from "@/components/sources-card";
import { VegaChart } from "@/components/vega-chart";
import { streamChat, type ChatMessage, type ChatFinal } from "@/lib/api";

export function Chat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  async function send() {
    const text = input.trim();
    if (!text || loading) return;
    const userMsg: ChatMessage = { role: "user", content: text };
    const assistantMsg: ChatMessage = { role: "assistant", content: "" };
    setMessages((m) => [...m, userMsg, assistantMsg]);
    setInput("");
    setLoading(true);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      await streamChat(
        [...messages, userMsg],
        (delta) => {
          setMessages((m) => {
            const copy = [...m];
            copy[copy.length - 1] = {
              ...copy[copy.length - 1],
              content: copy[copy.length - 1].content + delta,
            };
            return copy;
          });
        },
        (final: ChatFinal) => {
          setMessages((m) => {
            const copy = [...m];
            copy[copy.length - 1] = { ...copy[copy.length - 1], final };
            return copy;
          });
        },
        controller.signal
      );
    } catch (err) {
      setMessages((m) => {
        const copy = [...m];
        copy[copy.length - 1] = {
          ...copy[copy.length - 1],
          content: `Error: ${err instanceof Error ? err.message : String(err)}`,
        };
        return copy;
      });
    } finally {
      setLoading(false);
    }
  }

  function onKey(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  return (
    <Card className="flex h-[80vh] flex-col">
      <div className="flex items-center gap-2 border-b p-4">
        <span className="inline-block h-3 w-3 rounded-full bg-accent" aria-hidden />
        <span className="font-semibold">DATIA</span>
        <span className="text-sm text-muted-foreground">Habla con los datos de Colombia</span>
      </div>
      <ScrollArea className="flex-1 p-4">
        <div className="space-y-4">
          {messages.map((m, i) => (
            <div key={i} className="flex gap-3">
              <Avatar className="h-8 w-8">
                <AvatarFallback className={m.role === "user" ? "bg-muted" : "bg-accent text-accent-foreground"}>
                  {m.role === "user" ? "Tú" : "DA"}
                </AvatarFallback>
              </Avatar>
              <div className="min-w-0 flex-1">
                <div className="prose prose-sm max-w-none whitespace-pre-wrap">
                  {m.role === "assistant" ? (
                    <ReactMarkdown>{m.content || (loading && i === messages.length - 1 ? "…" : "")}</ReactMarkdown>
                  ) : (
                    m.content
                  )}
                </div>
                {m.final?.chart ? <VegaChart spec={m.final.chart} /> : null}
                {m.final?.citations ? <SourcesCard citations={m.final.citations} /> : null}
              </div>
            </div>
          ))}
        </div>
      </ScrollArea>
      <div className="flex items-center gap-2 border-t p-4">
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKey}
          placeholder="Preguntá sobre datos abiertos de Colombia…"
          disabled={loading}
        />
        <Button onClick={send} disabled={loading || !input.trim()}>
          {loading ? "…" : "Enviar"}
        </Button>
      </div>
    </Card>
  );
}

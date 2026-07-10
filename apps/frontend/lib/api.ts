// Client for the DATIA backend. Streams from POST /chat (SSE) and exposes helpers
// for the "Ver consulta" SoQL permalink.

export const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

export type Citation = {
  dataset: string;
  permalink: string;
  soql: string;
};

export type ChatFinal = {
  answer?: string;
  citations?: Citation[];
  chart?: Record<string, unknown>;
  soql?: string;
  dataset_id?: string;
};

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  final?: ChatFinal;
};

/**
 * Stream a chat answer from the backend.
 * Calls `onDelta` for incremental text and `onFinal` once with the structured payload
 * (citations + chart + soql). Parses the simple SSE format our FastAPI app emits:
 *   data: {"delta": "..."}\n\n
 *   data: {"final": {...}}\n\n
 *   event: done\ndata: {}\n\n
 */
export async function streamChat(
  messages: ChatMessage[],
  onDelta: (text: string) => void,
  onFinal: (final: ChatFinal) => void,
  signal?: AbortSignal
): Promise<void> {
  const res = await fetch(`${BACKEND_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages, stream: true }),
    signal,
  });

  if (!res.ok || !res.body) {
    throw new Error(`Backend error ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() || "";
    for (const evt of events) {
      const lines = evt.split("\n");
      for (const line of lines) {
        if (!line.startsWith("data:")) continue;
        const payload = line.slice(5).trim();
        if (!payload) continue;
        try {
          const obj = JSON.parse(payload);
          if (obj.delta) onDelta(obj.delta);
          if (obj.final) onFinal(obj.final);
        } catch {
          // ignore keepalives / non-JSON
        }
      }
    }
  }
}

/** Build a SoQL permalink on datos.gov.co for the "Ver consulta" button. */
export function soqlPermalink(datasetId: string, soql: string): string {
  const base = `https://www.datos.gov.co/resource/${datasetId}.json`;
  return soql ? `${base}?${soql.replace(/^\?/, "")}` : base;
}

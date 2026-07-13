// When NEXT_PUBLIC_BACKEND_URL is set (prod or explicit override), use it directly.
// Otherwise, route through the /proxy rewrite defined in next.config.ts (dev default).
export const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "/proxy";

export type Source = {
  name: string;
  permalink: string;
  soql: string;
};

export type ChatEvent =
  | { type: "thinking"; content: string }
  | { type: "query"; content: string; dataset: string }
  | { type: "answer"; content: string }
  | { type: "chart"; content: Record<string, unknown> }
  | { type: "sources"; content: Source[] };

export type InputMessage = {
  role: "user" | "assistant";
  content: string;
};

export async function streamChat(
  messages: InputMessage[],
  onEvent: (event: ChatEvent) => void,
  signal?: AbortSignal
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${BACKEND_URL}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages, stream: true }),
      signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new TypeError(
      "No se pudo conectar con el servidor. ¿Está el backend funcionando?"
    );
  }

  if (!res.ok || !res.body) {
    const detail = await res.text().catch(() => "");
    throw new Error(
      detail
        ? `Error del servidor (${res.status}): ${detail.slice(0, 300)}`
        : `Error del servidor: ${res.status}`
    );
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() || "";
    for (const chunk of chunks) {
      parseSSEChunk(chunk, onEvent);
    }
  }

  if (buffer.trim()) {
    parseSSEChunk(buffer, onEvent);
  }
}

function parseSSEChunk(chunk: string, onEvent: (event: ChatEvent) => void): void {
  const lines = chunk.split("\n");
  for (const line of lines) {
    if (!line.startsWith("data:")) continue;
    const payload = line.slice(5).trim();
    if (payload === "[DONE]" || !payload) continue;
    try {
      const obj = JSON.parse(payload);
      if (obj.type) onEvent(obj as ChatEvent);
    } catch {
      // ignore non-JSON payloads
    }
  }
}

export function soqlPermalink(datasetId: string, soql: string): string {
  const base = `https://www.datos.gov.co/d/${datasetId}`;
  return soql ? `${base}?${soql.replace(/^\?/, "")}` : base;
}

export function extractDatasetId(permalink: string): string {
  const match = permalink.match(/\/d\/([^/?]+)/);
  return match ? match[1] : permalink.split("/").pop() || "";
}

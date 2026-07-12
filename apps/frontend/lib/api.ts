export const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

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
  const res = await fetch(`${BACKEND_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages, stream: true }),
    signal,
  });

  if (!res.ok || !res.body) {
    throw new Error(`Error del servidor: ${res.status}`);
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
      const lines = chunk.split("\n");
      for (const line of lines) {
        if (!line.startsWith("data:")) continue;
        const payload = line.slice(5).trim();
        if (payload === "[DONE]") return;
        if (!payload) continue;
        try {
          const obj = JSON.parse(payload);
          if (obj.type) onEvent(obj as ChatEvent);
        } catch {
          // ignore non-JSON payloads
        }
      }
    }
  }
}

export function soqlPermalink(datasetId: string, soql: string): string {
  const base = `https://www.datos.gov.co/resource/${datasetId}.json`;
  return soql ? `${base}?${soql.replace(/^\?/, "")}` : base;
}

export function extractDatasetId(permalink: string): string {
  const match = permalink.match(/\/d\/([^/?]+)/);
  return match ? match[1] : permalink.split("/").pop() || "";
}

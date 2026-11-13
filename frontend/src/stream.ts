import type { Message, Source, Usage } from "./types";

export type StreamEvent = { event: string; data: Record<string, unknown> };

export async function* readEvents(stream: ReadableStream<Uint8Array>): AsyncGenerator<StreamEvent> {
  const reader = stream.getReader(),
    decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      let match: RegExpExecArray | null;
      while ((match = /\r?\n\r?\n/.exec(buffer))) {
        const frame = buffer.slice(0, match.index);
        buffer = buffer.slice(match.index + match[0].length);
        let event = "message";
        const data: string[] = [];
        for (const line of frame.split(/\r?\n/)) {
          if (line.startsWith("event:")) event = line.slice(6).trim();
          if (line.startsWith("data:"))
            data.push(line.slice(5).replace(/^ /, ""));
        }
        if (data.length) yield { event, data: JSON.parse(data.join("\n")) };
      }
      if (done) break;
    }
  } finally {
    reader.releaseLock();
  }
}

/** Fold one server event into the message list. `answer` is the running generation's ID. */
export function applyEvent(messages: Message[], e: StreamEvent, answer: string | undefined, model: string): Message[] {
  const patch = (change: (m: Message) => Message) =>
    messages.map((m) => (m.role === "assistant" && m.generation_id === answer ? change(m) : m));
  switch (e.event) {
    case "start":
      return [
        ...messages,
        {
          id: String(e.data.assistant_message_id),
          role: "assistant",
          content: "",
          generation_id: String(e.data.generation_id),
          status: "streaming",
          model_id: model,
        },
      ];
    case "delta":
      return patch((m) => ({ ...m, content: m.content + String(e.data.text ?? "") }));
    case "sources":
      return patch((m) => ({ ...m, citations: (e.data.sources ?? []) as Source[] }));
    case "done":
      return patch((m) => ({ ...m, status: "completed", usage: e.data.usage as Usage }));
    default:
      return messages;
  }
}

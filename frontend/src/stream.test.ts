import { expect, test } from "vitest";
import { applyEvent, readEvents } from "./stream";
test("parses split UTF-8, CRLF, comments and terminal events", async () => {
  const bytes = new TextEncoder().encode(
    ': heartbeat\r\nevent: delta\r\ndata: {"text":"hé"}\r\n\r\nevent: done\ndata: {"status":"succeeded"}\n\n',
  );
  const stream = new ReadableStream<Uint8Array>({
    start(c) {
      for (const b of bytes) c.enqueue(Uint8Array.of(b));
      c.close();
    },
  });
  const events = [];
  for await (const e of readEvents(stream)) events.push(e);
  expect(events).toEqual([
    { event: "delta", data: { text: "hé" } },
    { event: "done", data: { status: "succeeded" } },
  ]);
});
test("rejects malformed data and discards incomplete frames", async () => {
  const response = new Response("event: delta\ndata: invalid\n\n");
  await expect(async () => {
    for await (const _ of readEvents(response.body!)) {
      void _;
    }
  }).rejects.toThrow();
  const events = [];
  for await (const e of readEvents(new Response("data: {}").body!))
    events.push(e);
  expect(events).toEqual([]);
});

test("folds start, delta, sources and done into one answer", () => {
  const events = [
    { event: "start", data: { generation_id: "g1", assistant_message_id: "a1" } },
    { event: "delta", data: { text: "Hel" } },
    { event: "delta", data: { text: "lo" } },
    { event: "sources", data: { sources: [{ id: "1", name: "notes.txt" }] } },
    { event: "done", data: { usage: { total_tokens: 3 } } },
  ];
  let messages = [{ id: "u1", role: "user", content: "hi" }];
  let id: string | undefined;
  for (const e of events) {
    if (e.event === "start") id = String(e.data.generation_id);
    messages = applyEvent(messages, e, id, "m");
  }
  expect(messages[1]).toMatchObject({ id: "a1", content: "Hello", status: "completed", model_id: "m", citations: [{ id: "1" }] });
  expect(messages[0].content).toBe("hi");
});

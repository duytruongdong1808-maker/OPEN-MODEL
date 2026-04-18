export async function parseEventStream(
  stream: ReadableStream<Uint8Array>,
  onEvent: (eventName: string, payload: unknown) => void,
): Promise<void> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";

    for (const frame of frames) {
      const lines = frame.split("\n");
      let eventName = "message";
      let payload = "";

      for (const line of lines) {
        if (line.startsWith("event: ")) {
          eventName = line.slice("event: ".length).trim();
        } else if (line.startsWith("data: ")) {
          payload += line.slice("data: ".length);
        }
      }

      if (payload) {
        onEvent(eventName, JSON.parse(payload));
      }
    }
  }

  if (buffer.trim()) {
    const eventLine = buffer.split("\n").find((line) => line.startsWith("event: "));
    const dataLine = buffer.split("\n").find((line) => line.startsWith("data: "));
    if (dataLine) {
      onEvent(eventLine ? eventLine.slice("event: ".length).trim() : "message", JSON.parse(dataLine.slice(6)));
    }
  }
}

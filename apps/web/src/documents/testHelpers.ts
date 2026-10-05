export function deferred<T = unknown>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

// jsdom has File metadata but not the browser File.text/arrayBuffer methods.
export function textFile(name = "notes.md", content = "Ghi chú tiếng Việt", lastModified = 1) {
  const file = new File([content], name, { lastModified });
  Object.defineProperty(file, "text", { value: async () => content, configurable: true });
  Object.defineProperty(file, "arrayBuffer", { value: async () => new TextEncoder().encode(content).buffer, configurable: true });
  return file;
}

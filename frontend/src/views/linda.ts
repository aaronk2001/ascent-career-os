import { api } from "../api";
import type { View } from "../router";
import { $, esc } from "../ui";
import { mountOrb } from "../visuals";

type Msg = { role: "user" | "linda"; text: string; ts?: string };
type HistEntry = { query: string; answer: string; ts?: string };

const nowISO = () => new Date().toISOString();
const fmtTime = (ts?: string) => {
  if (!ts) return "";
  const d = new Date(ts);
  return isNaN(+d) ? "" : d.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
};

export default function linda(): View {
  const log: Msg[] = [];
  let status = "";
  let disposeOrb: (() => void) | undefined;

  return {
    cleanup() { disposeOrb?.(); },
    async render(root) {
      root.innerHTML = `
        <div class="flex flex-col h-[calc(100vh-4rem)] max-w-3xl mx-auto">
          <div class="flex items-center justify-between px-2 py-2">
            <div class="flex items-center gap-2.5"><div id="orb"></div><h1 class="text-2xl font-semibold tracking-tight">Linda</h1></div>
            <div class="flex items-center gap-3">
              <button id="export" class="text-xs text-fg-faint hover:text-fg">Export</button>
              <button id="clear" class="text-xs text-fg-faint hover:text-danger">Clear</button>
            </div>
          </div>
          <div id="log" class="flex-1 overflow-y-auto space-y-3 px-2 py-2"></div>
          <div id="status" class="px-3 h-5 text-xs text-brand-400"></div>
          <div class="card p-2 flex gap-2 m-2">
            <input id="q" placeholder="Ask Linda about your job search…" class="flex-1 bg-ink-800 rounded-lg px-3 py-2 text-sm" autofocus />
            <button id="send" class="rounded-lg btn-accent px-4 py-2 text-sm">Send</button>
          </div>
        </div>`;

      try {
        const { entries } = await api<{ entries: HistEntry[] }>("/agent/history?limit=10");
        for (const e of entries) {
          log.push({ role: "user", text: e.query, ts: e.ts }, { role: "linda", text: e.answer, ts: e.ts });
        }
      } catch {
        /* history optional */
      }
      paint(root);
      const orbEl = $(root, "#orb");
      if (orbEl) disposeOrb = mountOrb(orbEl, () => status !== "", 40);

      const input = $(root, "#q") as HTMLInputElement;
      const send = () => ask(root, input.value.trim());
      $(root, "#send")?.addEventListener("click", send);
      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") send();
      });
      $(root, "#clear")?.addEventListener("click", async () => {
        log.length = 0;
        paint(root);
        await api("/agent/history", { method: "DELETE" });
      });
      $(root, "#export")?.addEventListener("click", () => exportChat());
    },
  };

  function setStatus(root: HTMLElement, s: string) {
    status = s;
    const el = $(root, "#status");
    if (el) el.textContent = s;
  }

  function paint(root: HTMLElement) {
    const box = $(root, "#log");
    if (!box) return;
    box.innerHTML = log
      .map(
        (m) =>
          `<div class="flex flex-col ${m.role === "user" ? "items-end" : "items-start"}">
            <div class="max-w-[80%] rounded-card px-3 py-2 text-sm whitespace-pre-wrap ${m.role === "user" ? "accent-bg" : "card"}">${esc(m.text) || "…"}</div>
            ${m.ts ? `<div class="text-[10px] text-fg-faint nums mt-0.5 px-1">${esc(fmtTime(m.ts))}</div>` : ""}
          </div>`,
      )
      .join("");
    box.scrollTop = box.scrollHeight;
  }

  function exportChat() {
    if (!log.length) return;
    const md = `# Linda chat — exported ${new Date().toLocaleString()}\n\n` +
      log.map((m) => `**${m.role === "user" ? "Me" : "Linda"}**${m.ts ? ` · ${fmtTime(m.ts)}` : ""}\n\n${m.text}`).join("\n\n---\n\n") + "\n";
    const url = URL.createObjectURL(new Blob([md], { type: "text/markdown" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `linda-chat-${new Date().toISOString().slice(0, 10)}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function ask(root: HTMLElement, query: string) {
    if (!query || status) return;
    const input = $(root, "#q") as HTMLInputElement;
    input.value = "";
    log.push({ role: "user", text: query, ts: nowISO() });
    const reply: Msg = { role: "linda", text: "", ts: nowISO() };
    log.push(reply);
    paint(root);
    setStatus(root, "Thinking…");

    let res: Response;
    try {
      res = await fetch("/api/agent/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
      });
    } catch (e) {
      reply.text = `Connection error: ${String(e)}`;
      setStatus(root, "");
      paint(root);
      return;
    }
    if (!res.body) {
      reply.text = `Error: ${res.status}`;
      setStatus(root, "");
      paint(root);
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const lines = buf.split("\n");
      buf = lines.pop() ?? "";
      for (const line of lines) {
        if (!line.startsWith("data:")) continue;
        let ev: { type?: string; text?: string; tool?: string };
        try {
          ev = JSON.parse(line.slice(5).trim());
        } catch {
          continue;
        }
        switch (ev.type) {
          case "thinking":
            setStatus(root, "Thinking…");
            break;
          case "tool_start":
            setStatus(root, `🔧 ${ev.tool ?? "tool"}…`);
            break;
          case "tool_end":
          case "tool_skip":
          case "tool_error":
            setStatus(root, "Thinking…");
            break;
          case "answer":
            if (typeof ev.text === "string") {
              reply.text += ev.text;
              setStatus(root, "");
              paint(root);
            }
            break;
        }
      }
    }
    setStatus(root, "");
    if (reply.text) {
      void api("/agent/history", {
        method: "POST",
        body: JSON.stringify({ query, answer: reply.text }),
      }).catch(() => {});
    }
  }
}

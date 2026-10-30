import { useEffect, useState } from "react";

import { api } from "./api";

type Readiness = {
  status: string;
  dependencies: Record<string, { ok: boolean; detail: string }>;
};

type State =
  { kind: "loading" } | { kind: "ready"; data: Readiness } | { kind: "error"; message: string };

export function App() {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    api
      .GET("/ready")
      .then(({ data, error, response }) => {
        if (cancelled) return;
        const body = (data ?? error) as Readiness | undefined;
        if (body?.dependencies) setState({ kind: "ready", data: body });
        else setState({ kind: "error", message: `API answered HTTP ${response.status}` });
      })
      .catch((err: unknown) => {
        if (!cancelled) setState({ kind: "error", message: String(err) });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-8 px-6 py-16">
      <header>
        <h1 className="text-4xl font-semibold tracking-tight">
          Nadjet <span className="text-slate-400">— نجاة</span>
        </h1>
        <p className="mt-2 text-slate-400">
          Road-incident detection and emergency coordination platform.
        </p>
      </header>

      <section aria-labelledby="status-title" className="rounded-xl border border-slate-800 p-6">
        <h2 id="status-title" className="text-lg font-medium">
          System status
        </h2>
        {state.kind === "loading" && <p className="mt-3 text-slate-400">Checking the API…</p>}
        {state.kind === "error" && (
          <p className="mt-3 text-amber-400">API unreachable: {state.message}. Run `make dev`.</p>
        )}
        {state.kind === "ready" && (
          <ul className="mt-3 space-y-2">
            {Object.entries(state.data.dependencies).map(([name, dep]) => (
              <li key={name} className="flex items-center gap-3">
                <span className={dep.ok ? "text-emerald-400" : "text-red-400"}>
                  {dep.ok ? "OK" : "DOWN"}
                </span>
                <span className="font-mono">{name}</span>
                <span className="text-slate-400">{dep.detail}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}

import { useNavigate } from "@tanstack/react-router";
import { SearchIcon } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api } from "@/api";
import { cn } from "@/lib/utils";

/**
 * Figma "Search" bar of the control header: jumps to an incident by its short code (the code
 * read over the radio or in an SMS, e.g. 7F3). Searches the latest 200 incidents, open or not.
 */
export function IncidentSearch({ className }: { className?: string }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [code, setCode] = useState("");
  const [missing, setMissing] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const wanted = code.trim().toUpperCase();
    if (!wanted) return;
    setBusy(true);
    const { data } = await api
      .GET("/incidents", { params: { query: { limit: 200, open_only: false } } })
      .catch(() => ({ data: undefined }));
    setBusy(false);
    const match = data?.items.find((incident) => incident.short_code.toUpperCase() === wanted);
    if (match) {
      setMissing(null);
      setCode("");
      void navigate({ to: "/ops/incidents/$incidentId", params: { incidentId: match.id } });
    } else {
      setMissing(wanted);
    }
  }

  return (
    <form
      role="search"
      onSubmit={(event) => void submit(event)}
      className={cn("flex min-w-0 flex-1 flex-col gap-1 sm:max-w-md", className)}
    >
      <label className="relative flex items-center">
        <span className="sr-only">{t("common.searchIncident")}</span>
        <SearchIcon
          aria-hidden
          className="pointer-events-none absolute start-4 size-[18px] text-primary"
        />
        <input
          value={code}
          onChange={(event) => {
            setCode(event.target.value);
            setMissing(null);
          }}
          placeholder={t("common.searchIncident")}
          aria-invalid={missing ? true : undefined}
          aria-busy={busy || undefined}
          className="h-11 w-full rounded-xl border border-transparent bg-accent ps-11 pe-4 text-body-md font-medium text-ink outline-none placeholder:font-normal placeholder:text-primary/80 focus-visible:border-ring focus-visible:bg-card focus-visible:shadow-focus"
        />
      </label>
      {missing ? (
        <p role="status" className="px-1 text-body-xs text-danger">
          {t("common.searchNotFound", { code: missing })}
        </p>
      ) : null}
    </form>
  );
}

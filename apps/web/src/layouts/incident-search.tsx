import { useNavigate } from "@tanstack/react-router";
import { HouseIcon } from "lucide-react";
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
      className={cn("flex min-w-0 flex-1 flex-col gap-1 sm:max-w-[25rem]", className)}
    >
      <label className="relative flex items-center">
        <span className="sr-only">{t("common.searchIncident")}</span>
        <HouseIcon
          aria-hidden
          className="pointer-events-none absolute start-4 size-[18px] text-white"
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
          className="h-[42px] w-full rounded-xl border border-transparent bg-brand-200 ps-11 pe-4 text-body-md font-medium text-white shadow-[0_6px_20px_rgb(112_144_176/0.2)] outline-none placeholder:text-white focus-visible:bg-brand-300 focus-visible:shadow-focus"
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

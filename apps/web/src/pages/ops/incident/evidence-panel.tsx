import { DownloadIcon, ImageIcon, PlayIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";

import { fetchEvidence, type IncidentDetail } from "./incident-queries";

type Evidence = IncidentDetail["evidence"][number];
type Loaded = { url: string } | { error: true } | null;

/**
 * Loads one evidence file on demand with the session token and exposes an object URL.
 * Each load is a view recorded by the audit log (FR-SEC-004), so nothing loads on page open.
 */
function useEvidenceFile(incidentId: string, evidenceId: string) {
  const [state, setState] = useState<Loaded>(null);
  const [loading, setLoading] = useState(false);
  useEffect(
    () => () => {
      if (state && "url" in state) URL.revokeObjectURL(state.url);
    },
    [state],
  );
  async function load(): Promise<string | null> {
    if (state && "url" in state) return state.url;
    setLoading(true);
    try {
      const url = URL.createObjectURL(await fetchEvidence(incidentId, evidenceId));
      setState({ url });
      return url;
    } catch {
      setState({ error: true });
      return null;
    } finally {
      setLoading(false);
    }
  }
  return { state, loading, load };
}

function Failed() {
  const { t } = useTranslation();
  return (
    <p role="alert" className="text-body-sm text-danger">
      {t("ops.evidence.failed")}
    </p>
  );
}

function download(url: string, name: string) {
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
}

function ClipPlayer({ incidentId, clip }: { incidentId: string; clip: Evidence }) {
  const { t } = useTranslation();
  const { state, loading, load } = useEvidenceFile(incidentId, clip.id);
  return (
    <div className="flex flex-col gap-2">
      {state && "url" in state ? (
        <video
          src={state.url}
          controls
          autoPlay
          className="max-h-96 w-full rounded-lg bg-black"
          aria-label={t("ops.evidence.clip")}
        />
      ) : (
        <Button variant="outline" onClick={() => void load()} disabled={loading} className="w-fit">
          <PlayIcon aria-hidden />
          {t("ops.evidence.loadClip")}
        </Button>
      )}
      {state && "error" in state ? <Failed /> : null}
      <Button
        variant="ghost"
        size="sm"
        className="w-fit"
        onClick={() => void load().then((url) => url && download(url, `${clip.id}.mp4`))}
      >
        <DownloadIcon aria-hidden />
        {t("ops.evidence.download")}
      </Button>
    </div>
  );
}

function Keyframe({
  incidentId,
  frame,
  index,
}: {
  incidentId: string;
  frame: Evidence;
  index: number;
}) {
  const { t } = useTranslation();
  const { state, loading, load } = useEvidenceFile(incidentId, frame.id);
  const name = t("ops.evidence.keyframe", { index: index + 1 });
  return (
    <li className="flex flex-col gap-1">
      {state && "url" in state ? (
        <img src={state.url} alt={name} className="aspect-video w-full rounded-lg object-cover" />
      ) : (
        <Button
          variant="outline"
          className="aspect-video h-auto w-full flex-col"
          onClick={() => void load()}
          disabled={loading}
        >
          <ImageIcon aria-hidden />
          {name}
        </Button>
      )}
      {state && "error" in state ? <Failed /> : null}
      <Button
        variant="ghost"
        size="xs"
        className="w-fit"
        onClick={() => void load().then((url) => url && download(url, `${frame.id}.jpg`))}
      >
        <DownloadIcon aria-hidden />
        {t("ops.evidence.download")}
      </Button>
    </li>
  );
}

/** Evidence clip player and keyframes; viewing and downloading are audited. */
export function EvidencePanel({ incident }: { incident: IncidentDetail }) {
  const { t } = useTranslation();
  const clips = incident.evidence.filter((e) => e.kind === "clip");
  const frames = incident.evidence.filter((e) => e.kind !== "clip");
  if (incident.evidence.length === 0) {
    return <p className="text-muted-foreground">{t("ops.evidence.none")}</p>;
  }
  return (
    <div className="flex flex-col gap-4">
      <p className="text-body-xs text-muted-foreground">{t("ops.evidence.audited")}</p>
      {clips.map((clip) => (
        <ClipPlayer key={clip.id} incidentId={incident.id} clip={clip} />
      ))}
      {frames.length > 0 ? (
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {frames.map((frame, index) => (
            <Keyframe key={frame.id} incidentId={incident.id} frame={frame} index={index} />
          ))}
        </ul>
      ) : null}
    </div>
  );
}

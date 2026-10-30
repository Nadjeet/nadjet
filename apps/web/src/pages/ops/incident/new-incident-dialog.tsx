import { MapPinIcon } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

import { ApiError, useCreateIncident, type ManualIncident } from "@/lib/incident-queries";
import type { PickedPoint } from "./ops-map";

const SCENE = [
  "bus_involved",
  "person_on_road",
  "flames",
  "smoke",
  "overturned",
  "stopped_in_lane",
  "trapped",
] as const;
type SceneFlag = (typeof SCENE)[number];

function parseCoordinate(value: string, limit: number): number | null {
  const number = Number(value.replace(",", "."));
  return value.trim() !== "" && Number.isFinite(number) && Math.abs(number) <= limit
    ? number
    : null;
}

/**
 * Manual incident from a phone call (FR-INC-007). The point comes from a click on the map
 * ("Pick on map") or from the coordinate fields, which keep the form usable by keyboard.
 */
export function NewIncidentDialog({
  open,
  onOpenChange,
  picked,
  onPickOnMap,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  picked: PickedPoint | null;
  onPickOnMap: () => void;
  onCreated: (id: string) => void;
}) {
  const { t } = useTranslation();
  const create = useCreateIncident();
  const [typed, setTyped] = useState<{ lat: string; lon: string } | null>(null);
  const [notes, setNotes] = useState("");
  const [vehicles, setVehicles] = useState("");
  const [people, setPeople] = useState("");
  const [flags, setFlags] = useState<Record<SceneFlag, boolean>>({
    bus_involved: false,
    person_on_road: false,
    flames: false,
    smoke: false,
    overturned: false,
    stopped_in_lane: false,
    trapped: false,
  });

  // Typing wins over the map until the next pick replaces it.
  const lastPick = picked ? `${picked.lat}|${picked.lon}` : "";
  const [seenPick, setSeenPick] = useState(lastPick);
  if (seenPick !== lastPick) {
    setSeenPick(lastPick);
    setTyped(null);
  }
  const latText = typed?.lat ?? (picked ? picked.lat.toFixed(5) : "");
  const lonText = typed?.lon ?? (picked ? picked.lon.toFixed(5) : "");
  const lat = parseCoordinate(latText, 90);
  const lon = parseCoordinate(lonText, 180);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (lat === null || lon === null) return;
    const count = (value: string) => (value.trim() === "" ? null : Math.max(0, Number(value)));
    const body: ManualIncident = {
      location: { lat, lon },
      vehicle_count: count(vehicles) === null ? null : Math.min(50, count(vehicles) ?? 0),
      people_reported: count(people),
      notes: notes.trim() === "" ? null : notes.trim(),
      ...flags,
    };
    create.mutate(body, {
      onSuccess: (created) => {
        onOpenChange(false);
        setNotes("");
        setVehicles("");
        setPeople("");
        setTyped(null);
        onCreated(created.id);
      },
    });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto">
        <form onSubmit={submit} className="flex flex-col gap-4">
          <DialogHeader>
            <DialogTitle>{t("ops.create.title")}</DialogTitle>
            <DialogDescription>{t("ops.create.description")}</DialogDescription>
          </DialogHeader>
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex flex-col gap-1">
              <Label htmlFor="new-lat">{t("ops.create.lat")}</Label>
              <Input
                id="new-lat"
                dir="ltr"
                inputMode="decimal"
                className="w-36"
                value={latText}
                aria-invalid={latText !== "" && lat === null}
                onChange={(e) => setTyped({ lat: e.target.value, lon: lonText })}
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="new-lon">{t("ops.create.lon")}</Label>
              <Input
                id="new-lon"
                dir="ltr"
                inputMode="decimal"
                className="w-36"
                value={lonText}
                aria-invalid={lonText !== "" && lon === null}
                onChange={(e) => setTyped({ lat: latText, lon: e.target.value })}
              />
            </div>
            <Button type="button" variant="outline" onClick={onPickOnMap}>
              <MapPinIcon aria-hidden />
              {t("ops.create.pick")}
            </Button>
          </div>
          <fieldset className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <legend className="mb-2 text-body-sm font-medium">{t("ops.create.scene")}</legend>
            {SCENE.map((flag) => (
              <div key={flag} className="flex items-center gap-3">
                <Checkbox
                  id={`new-${flag}`}
                  checked={flags[flag]}
                  onCheckedChange={(checked) =>
                    setFlags((current) => ({ ...current, [flag]: checked === true }))
                  }
                />
                <Label htmlFor={`new-${flag}`}>{t(`ops.create.flags.${flag}`)}</Label>
              </div>
            ))}
          </fieldset>
          <div className="flex flex-wrap gap-3">
            <div className="flex flex-col gap-1">
              <Label htmlFor="new-vehicles">{t("ops.create.vehicles")}</Label>
              <Input
                id="new-vehicles"
                type="number"
                min={0}
                max={50}
                className="w-32"
                value={vehicles}
                onChange={(e) => setVehicles(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="new-people">{t("ops.create.people")}</Label>
              <Input
                id="new-people"
                type="number"
                min={0}
                className="w-32"
                value={people}
                onChange={(e) => setPeople(e.target.value)}
              />
            </div>
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="new-notes">{t("ops.create.notes")}</Label>
            <Textarea
              id="new-notes"
              maxLength={1000}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </div>
          {create.isError ? (
            <p role="alert" className="text-body-sm text-danger">
              {create.error instanceof ApiError && create.error.status === 403
                ? t("ops.errors.forbidden")
                : t("ops.errors.generic")}
            </p>
          ) : null}
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              {t("ops.actions.cancel")}
            </Button>
            <Button type="submit" disabled={lat === null || lon === null || create.isPending}>
              {t("ops.create.submit")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

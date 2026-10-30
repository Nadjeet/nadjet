import { CircleCheckIcon, SirenIcon, TriangleAlertIcon } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { SimulatedLabel } from "@/components/incident/simulated-label";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Skeleton } from "@/components/ui/skeleton";
import { useLabel } from "@/lib/format";

import {
  ApiError,
  useChangeHospital,
  useDispatch,
  useDispatches,
  useRecommendations,
  type DispatchRow,
  type IncidentDetail,
  type RankedResource,
} from "./incident-queries";
import { RouteMap, type RouteLine } from "./route-map";

const FIELD_STATUSES = new Set(["acknowledged", "en_route", "on_scene", "transporting"]);

function minutes(seconds: number): number {
  return Math.max(1, Math.round(seconds / 60));
}

function useErrorText() {
  const { t } = useTranslation();
  return (error: unknown) => {
    if (error instanceof ApiError) {
      if (error.status === 409) return t("ops.errors.conflict");
      if (error.status === 503) return t("ops.errors.routing");
      if (error.status === 403) return t("ops.errors.forbidden");
    }
    return t("ops.errors.generic");
  };
}

/** ETA, distance, agency and Ready/Divert state of one candidate (text and icon, not colour). */
function ResourceFacts({ resource }: { resource: RankedResource }) {
  const { t } = useTranslation();
  const label = useLabel();
  const capabilities = Object.entries(resource.capabilities ?? {})
    .filter(([, on]) => on === true)
    .map(([name]) => name);
  return (
    <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-body-sm">
      <span className="font-medium">{resource.name}</span>
      <span>{t("ops.dispatch.eta", { minutes: minutes(resource.eta_s) })}</span>
      <span className="text-muted-foreground">
        {t("ops.dispatch.distance", { km: (resource.distance_m / 1000).toFixed(1) })}
      </span>
      {resource.agency ? (
        <Badge variant="outline">{label(`ops.agency.${resource.agency}`, resource.agency)}</Badge>
      ) : null}
      {capabilities.map((name) => (
        <Badge key={name} variant="secondary">
          {label(`ops.capability.${name}`, name)}
        </Badge>
      ))}
      {resource.kind === "hospital" && resource.ready_state ? (
        <Badge variant="outline">
          {resource.ready_state === "ready" ? (
            <CircleCheckIcon aria-hidden />
          ) : (
            <TriangleAlertIcon aria-hidden />
          )}
          {resource.ready_state === "ready" ? t("ops.dispatch.ready") : t("ops.dispatch.divert")}
        </Badge>
      ) : null}
      {resource.simulated ? <SimulatedLabel /> : null}
    </span>
  );
}

function routeLines(
  units: { id: string; name: string; geometry: RouteLine["geometry"] }[],
  hospital: { id: string; name: string; geometry: RouteLine["geometry"] } | undefined,
  t: (key: "ops.dispatch.unitRoute" | "ops.dispatch.hospitalRoute", o: { name: string }) => string,
): RouteLine[] {
  return [
    ...units.map((u) => ({
      id: `unit-${u.id}`,
      kind: "unit" as const,
      label: t("ops.dispatch.unitRoute", { name: u.name }),
      geometry: u.geometry,
    })),
    ...(hospital
      ? [
          {
            id: `hospital-${hospital.id}`,
            kind: "hospital" as const,
            label: t("ops.dispatch.hospitalRoute", { name: hospital.name }),
            geometry: hospital.geometry,
          },
        ]
      : []),
  ];
}

/** Choose units and a hospital from the ranking and confirm in one action (FR-DSP-003). */
function DispatchChooser({ incident }: { incident: IncidentDetail }) {
  const { t } = useTranslation();
  const label = useLabel();
  const errorText = useErrorText();
  const recommendations = useRecommendations(incident.id, true);
  const dispatch = useDispatch(incident.id);
  const [units, setUnits] = useState<string[]>([]);
  const [hospital, setHospital] = useState("");
  const data = recommendations.data;

  const selectedUnits = useMemo(
    () => (data?.units ?? []).filter((u) => units.includes(u.id)),
    [data, units],
  );
  const selectedHospital = data?.hospitals.find((h) => h.id === hospital);
  const lines = routeLines(
    selectedUnits.map((u) => ({ id: u.id, name: u.name, geometry: u.route_geojson })),
    selectedHospital && {
      id: selectedHospital.id,
      name: selectedHospital.name,
      geometry: selectedHospital.route_geojson,
    },
    t,
  );

  if (recommendations.isPending) return <Skeleton className="h-40 w-full" />;
  if (recommendations.isError || !data) {
    return (
      <p role="alert" className="text-body-sm">
        {errorText(recommendations.error)}{" "}
        <Button variant="link" onClick={() => void recommendations.refetch()}>
          {t("common.retry")}
        </Button>
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-4">
      <p className="text-body-xs text-muted-foreground">
        {t("ops.dispatch.need", {
          agencies: data.unit_agencies
            .map((agency) => label(`ops.agency.${agency}`, agency))
            .join(", "),
          need: label(`ops.capability.${data.hospital_need}`, data.hospital_need),
        })}
      </p>
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 text-body-sm font-bold">{t("ops.dispatch.units")}</legend>
        {data.units.length === 0 ? (
          <p className="text-body-sm text-muted-foreground">{t("ops.dispatch.noUnits")}</p>
        ) : null}
        {data.units.map((unit) => (
          <div key={unit.id} className="flex items-start gap-3">
            <Checkbox
              id={`unit-${unit.id}`}
              className="mt-1"
              checked={units.includes(unit.id)}
              onCheckedChange={(checked) =>
                setUnits((current) =>
                  checked === true ? [...current, unit.id] : current.filter((id) => id !== unit.id),
                )
              }
            />
            <Label htmlFor={`unit-${unit.id}`} className="font-normal">
              <ResourceFacts resource={unit} />
            </Label>
          </div>
        ))}
      </fieldset>
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 text-body-sm font-bold">{t("ops.dispatch.hospitals")}</legend>
        {data.hospitals.length === 0 ? (
          <p className="text-body-sm text-muted-foreground">{t("ops.dispatch.noHospitals")}</p>
        ) : null}
        <RadioGroup value={hospital} onValueChange={setHospital}>
          {data.hospitals.map((h) => (
            <div key={h.id} className="flex items-start gap-3">
              <RadioGroupItem id={`hospital-${h.id}`} value={h.id} className="mt-1" />
              <Label htmlFor={`hospital-${h.id}`} className="font-normal">
                <ResourceFacts resource={h} />
              </Label>
            </div>
          ))}
        </RadioGroup>
      </fieldset>
      <RouteMap
        scene={
          incident.lat !== null && incident.lon !== null
            ? { lat: incident.lat, lon: incident.lon }
            : null
        }
        routes={lines}
        className="h-80 overflow-hidden rounded-lg border border-border"
      />
      {dispatch.isError ? (
        <p role="alert" className="text-body-sm text-danger">
          {errorText(dispatch.error)}
        </p>
      ) : null}
      <Button
        className="w-fit"
        disabled={units.length === 0 || !hospital || dispatch.isPending}
        onClick={() => dispatch.mutate({ unit_ids: units, hospital_id: hospital })}
      >
        <SirenIcon aria-hidden />
        {t("ops.dispatch.confirm", { count: units.length })}
      </Button>
    </div>
  );
}

/** Sent / delivered / failed per recipient channel, from the notification log (FR-NTF-003). */
function Deliveries({ row }: { row: DispatchRow }) {
  const { t } = useTranslation();
  if (row.deliveries.length === 0) {
    return <span className="text-muted-foreground">{t("ops.dispatch.noRecipients")}</span>;
  }
  return (
    <ul className="flex flex-wrap gap-2">
      {row.deliveries.map((delivery, index) => (
        <li key={index}>
          <Badge variant="outline">
            {t(`ops.dispatch.channel.${delivery.channel}`)} ·{" "}
            {t(`ops.dispatch.delivery.${delivery.status}`)}
          </Badge>
        </li>
      ))}
    </ul>
  );
}

function HospitalSwitch({
  incident,
  current,
  proposedId,
  proposedName,
}: {
  incident: IncidentDetail;
  current: DispatchRow;
  proposedId?: string;
  proposedName?: string;
}) {
  const { t } = useTranslation();
  const errorText = useErrorText();
  const recommendations = useRecommendations(incident.id, true);
  const change = useChangeHospital(incident.id);
  const [choice, setChoice] = useState(proposedId ?? "");
  const options = (recommendations.data?.hospitals ?? []).filter(
    (h) => h.id !== current.resource_id,
  );
  return (
    <div className="flex flex-col gap-3">
      <div
        role="alert"
        className="flex items-start gap-2 rounded-lg border border-dashed border-foreground/40 bg-muted px-4 py-3 text-body-sm"
      >
        <TriangleAlertIcon aria-hidden className="mt-0.5 size-4 shrink-0" />
        <span>
          {t("ops.dispatch.divertAlert", { name: current.name })}
          {proposedName ? ` ${t("ops.dispatch.proposed", { name: proposedName })}` : ""}
        </span>
      </div>
      <RadioGroup value={choice} onValueChange={setChoice} aria-label={t("ops.dispatch.hospitals")}>
        {options.map((h) => (
          <div key={h.id} className="flex items-start gap-3">
            <RadioGroupItem id={`switch-${h.id}`} value={h.id} className="mt-1" />
            <Label htmlFor={`switch-${h.id}`} className="font-normal">
              <ResourceFacts resource={h} />
              {h.id === proposedId ? (
                <Badge className="ms-2">{t("ops.dispatch.proposedTag")}</Badge>
              ) : null}
            </Label>
          </div>
        ))}
      </RadioGroup>
      {change.isError ? (
        <p role="alert" className="text-body-sm text-danger">
          {errorText(change.error)}
        </p>
      ) : null}
      <Button
        className="w-fit"
        disabled={!choice || change.isPending}
        onClick={() => change.mutate(choice)}
      >
        {t("ops.dispatch.switch")}
      </Button>
    </div>
  );
}

/** Dispatched resources with ETA, route and per-recipient delivery; DIVERT handling (E-10). */
function DispatchStatus({ incident }: { incident: IncidentDetail }) {
  const { t } = useTranslation();
  const dispatches = useDispatches(incident.id, true);
  if (dispatches.isPending) return <Skeleton className="h-32 w-full" />;
  if (dispatches.isError || !dispatches.data) {
    return <p role="alert">{t("ops.errors.generic")}</p>;
  }
  const active = dispatches.data.filter((d) => d.status === "dispatched");
  const hospital = active.find((d) => d.kind === "hospital");
  const diverted = [...incident.events]
    .reverse()
    .filter((e) => e.kind === "hospital_diverted")
    .map(
      (e) => e.payload as { facility_id?: string; proposed?: { id: string; name: string } | null },
    )
    .find((p) => p.facility_id === hospital?.resource_id);
  const lines = routeLines(
    active
      .filter((d) => d.kind === "unit")
      .map((d) => ({ id: d.resource_id, name: d.name, geometry: d.route_geojson })),
    hospital && { id: hospital.resource_id, name: hospital.name, geometry: hospital.route_geojson },
    t,
  );
  return (
    <div className="flex flex-col gap-4">
      {hospital && diverted ? (
        <HospitalSwitch
          incident={incident}
          current={hospital}
          proposedId={diverted.proposed?.id}
          proposedName={diverted.proposed?.name}
        />
      ) : null}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[34rem] text-start text-body-sm">
          <caption className="sr-only">{t("ops.dispatch.title")}</caption>
          <thead className="text-body-xs text-muted-foreground">
            <tr>
              {(["resource", "eta", "status", "delivery"] as const).map((col) => (
                <th key={col} scope="col" className="px-2 py-1 text-start font-medium">
                  {t(`ops.dispatch.col.${col}`)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {dispatches.data.map((row) => (
              <tr key={row.id} className="border-t border-border align-top">
                <th scope="row" className="px-2 py-2 text-start font-medium">
                  <span className="flex flex-wrap items-center gap-2">
                    {row.name}
                    <Badge variant="secondary">{t(`ops.dispatch.kind.${row.kind}`)}</Badge>
                    {row.simulated ? <SimulatedLabel /> : null}
                  </span>
                </th>
                <td className="px-2 py-2 whitespace-nowrap">
                  {t("ops.dispatch.eta", { minutes: minutes(row.eta_s) })} ·{" "}
                  {t("ops.dispatch.distance", { km: (row.distance_m / 1000).toFixed(1) })}
                </td>
                <td className="px-2 py-2">
                  {t(`ops.dispatch.status.${row.status}`)}
                  {row.status === "dispatched" && FIELD_STATUSES.has(incident.status) ? (
                    <span className="block text-body-xs text-muted-foreground">
                      {t("ops.dispatch.fieldAck", {
                        status: t(`status.${incident.status as "acknowledged"}`),
                      })}
                    </span>
                  ) : null}
                </td>
                <td className="px-2 py-2">
                  <Deliveries row={row} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <RouteMap
        scene={
          incident.lat !== null && incident.lon !== null
            ? { lat: incident.lat, lon: incident.lon }
            : null
        }
        routes={lines}
        className="h-80 overflow-hidden rounded-lg border border-border"
      />
    </div>
  );
}

const DISPATCH_VISIBLE = new Set([
  "verified",
  "dispatched",
  "acknowledged",
  "en_route",
  "on_scene",
  "transporting",
  "at_hospital",
  "closed",
]);

/** The operator's dispatch panel: pick resources while verified, follow them afterwards. */
export function DispatchPanel({ incident }: { incident: IncidentDetail }) {
  const { t } = useTranslation();
  if (!DISPATCH_VISIBLE.has(incident.status)) return null;
  if (incident.lat === null || incident.lon === null) {
    return <p className="text-body-sm">{t("ops.dispatch.noPosition")}</p>;
  }
  return incident.status === "verified" ? (
    <DispatchChooser incident={incident} />
  ) : (
    <DispatchStatus incident={incident} />
  );
}

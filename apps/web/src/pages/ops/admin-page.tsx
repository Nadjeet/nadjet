import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ChangeEvent, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import type { components } from "@nadjet/api-client";

import { api } from "@/api";
import { SimulatedLabel } from "@/components/incident/simulated-label";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Input, fieldClasses } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

type Schemas = components["schemas"];
type Camera = Schemas["AdminCamera"];
type Facility = Schemas["AdminFacility"];
type Unit = Schemas["AdminUnit"];
type UserRow = Schemas["AdminUserOut"];

const TABS = ["cameras", "facilities", "units", "users"] as const;
type Tab = (typeof TABS)[number];
const ROLES = ["operator", "supervisor", "responder", "hospital", "auditor", "admin"] as const;
const AGENCIES = ["civil_protection", "gendarmerie", "police", "samu"] as const;
const select = cn(fieldClasses, "h-10 text-body-sm");

/** The API answers refused changes with `{detail}`; show it as text. */
function detail(error: unknown): string {
  const d = (error as { detail?: unknown } | undefined)?.detail;
  return typeof d === "string" ? d : JSON.stringify(d ?? error);
}

function Status({ error, saved }: { error: string | null; saved: boolean }) {
  const { t } = useTranslation();
  if (error) return <p role="alert">{t("admin.error", { message: error })}</p>;
  return saved ? <p role="status">{t("admin.saved")}</p> : null;
}

/** Runs one admin request and reports the result; `refresh` reloads the list after a change. */
function useChange(listKey: string) {
  const client = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const mutation = useMutation({
    mutationFn: async (request: () => Promise<{ error?: unknown }>) => {
      const { error: failure } = await request();
      if (failure) throw new Error(detail(failure));
    },
    onMutate: () => {
      setError(null);
      setSaved(false);
    },
    onSuccess: async () => {
      setSaved(true);
      await client.invalidateQueries({ queryKey: ["admin", listKey] });
    },
    onError: (e: Error) => setError(e.message),
  });
  return { run: mutation.mutate, pending: mutation.isPending, error, saved };
}

function useList<T>(key: string, load: () => Promise<{ data?: T[]; error?: unknown }>) {
  return useQuery({
    queryKey: ["admin", key],
    queryFn: async () => {
      const { data, error } = await load();
      if (!data) throw new Error(detail(error));
      return data;
    },
  });
}

const th = "py-2 pe-3 text-start font-medium text-muted-foreground";

function Table({
  caption,
  head,
  children,
}: {
  caption: string;
  head: string[];
  children: React.ReactNode;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-start text-body-sm">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="border-b border-border">
            {head.map((h) => (
              <th key={h} scope="col" className={th}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

const cell = "py-2 pe-3 align-top";

// ------------------------------------------------------------------ cameras

function CameraRow({ camera }: { camera: Camera }) {
  const { t } = useTranslation();
  const change = useChange("cameras");
  const [draft, setDraft] = useState({
    name: camera.name,
    road: camera.road,
    wilaya: camera.wilaya,
    heading_deg: String(camera.heading_deg),
  });
  const [zonesError, setZonesError] = useState(false);
  const save = () =>
    change.run(() =>
      api.PATCH("/admin/cameras/{camera_id}", {
        params: { path: { camera_id: camera.id } },
        body: { ...draft, heading_deg: Number(draft.heading_deg) },
      }),
    );
  const upload = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    try {
      const zones: unknown = JSON.parse(await file.text());
      if (typeof zones !== "object" || zones === null || Array.isArray(zones)) throw new Error();
      setZonesError(false);
      change.run(() =>
        api.PUT("/admin/cameras/{camera_id}/zones", {
          params: { path: { camera_id: camera.id } },
          body: zones as Record<string, never>,
        }),
      );
    } catch {
      setZonesError(true);
    }
  };
  const field = (key: keyof typeof draft, label: string) => (
    <Input
      size="sm"
      aria-label={`${label} ${camera.id}`}
      value={draft[key]}
      onChange={(e) => setDraft({ ...draft, [key]: e.target.value })}
    />
  );
  return (
    <tr className="border-b border-border last:border-0">
      <th scope="row" className={cn(cell, "text-start font-medium")}>
        <bdi dir="ltr">{camera.id}</bdi>
        {camera.simulated ? <SimulatedLabel /> : null}
      </th>
      <td className={cell}>{field("name", t("admin.name"))}</td>
      <td className={cell}>{field("road", t("admin.road"))}</td>
      <td className={cell}>{field("wilaya", t("admin.wilaya"))}</td>
      <td className={cell}>{field("heading_deg", t("admin.heading"))}</td>
      <td className={cell}>
        <Label className="sr-only" htmlFor={`zones-${camera.id}`}>
          {t("admin.zones")} {camera.id}
        </Label>
        <input
          id={`zones-${camera.id}`}
          type="file"
          accept="application/json,.json"
          onChange={upload}
          className="text-body-xs"
        />
        {zonesError ? <p role="alert">{t("admin.zonesInvalid")}</p> : null}
      </td>
      <td className={cell}>
        <Button size="xs" onClick={save} disabled={change.pending}>
          {t("admin.save")}
        </Button>
        <Status error={change.error} saved={change.saved} />
      </td>
    </tr>
  );
}

function CamerasTab() {
  const { t } = useTranslation();
  const { data } = useList("cameras", () => api.GET("/admin/cameras"));
  return (
    <Table
      caption={t("admin.tabs.cameras")}
      head={[
        "ID",
        t("admin.name"),
        t("admin.road"),
        t("admin.wilaya"),
        t("admin.heading"),
        t("admin.zones"),
        "",
      ]}
    >
      {data?.map((camera) => (
        <CameraRow key={camera.id} camera={camera} />
      ))}
    </Table>
  );
}

// --------------------------------------------------------------- facilities

function FacilityRow({ facility }: { facility: Facility }) {
  const { t } = useTranslation();
  const change = useChange("facilities");
  const [name, setName] = useState(facility.name);
  const [ready, setReady] = useState(facility.ready_state);
  const [sms, setSms] = useState(facility.contact_sms ?? "");
  const [caps, setCaps] = useState(facility.capabilities);
  const save = () =>
    change.run(() =>
      api.PATCH("/admin/facilities/{facility_id}", {
        params: { path: { facility_id: facility.id } },
        body: { name, ready_state: ready, contact_sms: sms || null, capabilities: caps },
      }),
    );
  return (
    <tr className="border-b border-border last:border-0">
      <th scope="row" className={cn(cell, "text-start font-medium")}>
        <bdi dir="ltr">{facility.id}</bdi>
        {facility.simulated ? <SimulatedLabel /> : null}
      </th>
      <td className={cell}>
        <Input
          size="sm"
          aria-label={`${t("admin.name")} ${facility.id}`}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </td>
      <td className={cell}>
        <select
          className={select}
          aria-label={`${t("admin.readyState")} ${facility.id}`}
          value={ready}
          onChange={(e) => setReady(e.target.value as Facility["ready_state"])}
        >
          <option value="ready">{t("admin.ready")}</option>
          <option value="divert">{t("admin.divert")}</option>
        </select>
      </td>
      <td className={cell}>
        <Input
          size="sm"
          aria-label={`${t("admin.contactSms")} ${facility.id}`}
          value={sms}
          onChange={(e) => setSms(e.target.value)}
        />
      </td>
      <td className={cell}>
        <div className="flex flex-wrap gap-x-3 gap-y-1">
          {Object.entries(caps).map(([key, value]) => (
            <label key={key} className="flex items-center gap-1">
              <input
                type="checkbox"
                checked={value}
                onChange={(e) => setCaps({ ...caps, [key]: e.target.checked })}
              />
              {key}
            </label>
          ))}
        </div>
      </td>
      <td className={cell}>
        <Button size="xs" onClick={save} disabled={change.pending}>
          {t("admin.save")}
        </Button>
        <Status error={change.error} saved={change.saved} />
      </td>
    </tr>
  );
}

function FacilitiesTab() {
  const { t } = useTranslation();
  const { data } = useList("facilities", () => api.GET("/admin/facilities"));
  return (
    <Table
      caption={t("admin.tabs.facilities")}
      head={[
        "ID",
        t("admin.name"),
        t("admin.readyState"),
        t("admin.contactSms"),
        t("admin.capabilities"),
        "",
      ]}
    >
      {data?.map((facility) => (
        <FacilityRow key={facility.id} facility={facility} />
      ))}
    </Table>
  );
}

// -------------------------------------------------------------------- units

function UnitRow({ unit }: { unit: Unit }) {
  const { t } = useTranslation();
  const change = useChange("units");
  const [callsign, setCallsign] = useState(unit.callsign);
  const [status, setStatus] = useState(unit.status);
  const [phone, setPhone] = useState(unit.phone ?? "");
  const save = () =>
    change.run(() =>
      api.PATCH("/admin/units/{unit_id}", {
        params: { path: { unit_id: unit.id } },
        body: {
          callsign,
          phone: phone || null,
          // `dispatched` belongs to dispatch: only send a status the admin can set.
          ...(status === "dispatched" ? {} : { status }),
        },
      }),
    );
  return (
    <tr className="border-b border-border last:border-0">
      <th scope="row" className={cn(cell, "text-start font-medium")}>
        <bdi dir="ltr">{unit.id}</bdi>
        {unit.simulated ? <SimulatedLabel /> : null}
      </th>
      <td className={cell}>
        <Input
          size="sm"
          aria-label={`${t("admin.callsign")} ${unit.id}`}
          value={callsign}
          onChange={(e) => setCallsign(e.target.value)}
        />
      </td>
      <td className={cell}>
        <select
          className={select}
          aria-label={`${t("admin.status")} ${unit.id}`}
          value={status}
          onChange={(e) => setStatus(e.target.value as Unit["status"])}
        >
          {(["available", "dispatched", "busy", "offline"] as const).map((s) => (
            <option key={s} value={s} disabled={s === "dispatched" && unit.status !== "dispatched"}>
              {t(`admin.${s}`)}
            </option>
          ))}
        </select>
      </td>
      <td className={cell}>
        <Input
          size="sm"
          aria-label={`${t("admin.phone")} ${unit.id}`}
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
        />
      </td>
      <td className={cell}>
        <Button size="xs" onClick={save} disabled={change.pending}>
          {t("admin.save")}
        </Button>
        <Status error={change.error} saved={change.saved} />
      </td>
    </tr>
  );
}

function UnitsTab() {
  const { t } = useTranslation();
  const { data } = useList("units", () => api.GET("/admin/units"));
  return (
    <Table
      caption={t("admin.tabs.units")}
      head={["ID", t("admin.callsign"), t("admin.status"), t("admin.phone"), ""]}
    >
      {data?.map((unit) => (
        <UnitRow key={unit.id} unit={unit} />
      ))}
    </Table>
  );
}

// -------------------------------------------------------------------- users

function UserRowView({ user }: { user: UserRow }) {
  const { t } = useTranslation();
  const change = useChange("users");
  const [name, setName] = useState(user.display_name);
  const [phone, setPhone] = useState(user.phone ?? "");
  const [role, setRole] = useState(user.role);
  const [agency, setAgency] = useState(user.agency ?? "");
  const [facility, setFacility] = useState(user.facility_id ?? "");
  const [password, setPassword] = useState("");
  const patch = (body: Schemas["UserPatch"]) =>
    change.run(() =>
      api.PATCH("/admin/users/{user_id}", { params: { path: { user_id: user.id } }, body }),
    );
  const save = () => {
    patch({
      display_name: name,
      phone: phone || null,
      role,
      agency: role === "responder" ? ((agency || null) as UserRow["agency"]) : null,
      facility_id: role === "hospital" ? facility || null : null,
      ...(password ? { password } : {}),
    });
    setPassword("");
  };
  return (
    <tr className="border-b border-border last:border-0">
      <th scope="row" className={cn(cell, "text-start font-medium")}>
        <bdi dir="ltr">{user.username}</bdi>
        {user.active ? null : (
          <span className="block text-muted-foreground">{t("admin.inactive")}</span>
        )}
      </th>
      <td className={cell}>
        <Input
          size="sm"
          aria-label={`${t("admin.displayName")} ${user.username}`}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </td>
      <td className={cell}>
        <select
          className={select}
          aria-label={`${t("admin.role")} ${user.username}`}
          value={role}
          onChange={(e) => setRole(e.target.value as UserRow["role"])}
        >
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {t(`admin.roles.${r}`)}
            </option>
          ))}
        </select>
      </td>
      <td className={cell}>
        {role === "responder" ? (
          <select
            className={select}
            aria-label={`${t("admin.agency")} ${user.username}`}
            value={agency}
            onChange={(e) => setAgency(e.target.value)}
          >
            <option value="">{t("admin.noAgency")}</option>
            {AGENCIES.map((a) => (
              <option key={a} value={a}>
                {t(`admin.agencies.${a}`)}
              </option>
            ))}
          </select>
        ) : null}
        {role === "hospital" ? (
          <Input
            size="sm"
            aria-label={`${t("admin.facility")} ${user.username}`}
            value={facility}
            onChange={(e) => setFacility(e.target.value)}
          />
        ) : null}
      </td>
      <td className={cell}>
        <Input
          size="sm"
          aria-label={`${t("admin.phone")} ${user.username}`}
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
        />
      </td>
      <td className={cell}>
        <Input
          size="sm"
          type="password"
          autoComplete="new-password"
          aria-label={`${t("admin.newPassword")} ${user.username}`}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </td>
      <td className={cell}>
        <div className="flex flex-wrap gap-2">
          <Button size="xs" onClick={save} disabled={change.pending}>
            {t("admin.save")}
          </Button>
          <Button
            size="xs"
            variant={user.active ? "destructive" : "outline"}
            onClick={() => patch({ active: !user.active })}
            disabled={change.pending}
          >
            {user.active ? t("admin.deactivate") : t("admin.activate")}
          </Button>
        </div>
        <Status error={change.error} saved={change.saved} />
      </td>
    </tr>
  );
}

function NewUser() {
  const { t } = useTranslation();
  const change = useChange("users");
  const [form, setForm] = useState({
    username: "",
    display_name: "",
    password: "",
    role: "operator" as UserRow["role"],
    agency: "",
    facility_id: "",
  });
  const set = (key: keyof typeof form) => (e: ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm({ ...form, [key]: e.target.value });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    change.run(() =>
      api.POST("/admin/users", {
        body: {
          username: form.username,
          display_name: form.display_name,
          password: form.password,
          role: form.role,
          agency: form.role === "responder" ? ((form.agency || null) as UserRow["agency"]) : null,
          facility_id: form.role === "hospital" ? form.facility_id || null : null,
        },
      }),
    );
    setForm({ ...form, password: "" });
  };
  return (
    <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
      <div className="grid gap-1.5">
        <Label htmlFor="new-username">{t("admin.username")}</Label>
        <Input
          id="new-username"
          size="sm"
          required
          minLength={3}
          value={form.username}
          onChange={set("username")}
        />
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor="new-display">{t("admin.displayName")}</Label>
        <Input
          id="new-display"
          size="sm"
          required
          value={form.display_name}
          onChange={set("display_name")}
        />
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor="new-password">{t("admin.password")}</Label>
        <Input
          id="new-password"
          size="sm"
          type="password"
          autoComplete="new-password"
          required
          minLength={12}
          value={form.password}
          onChange={set("password")}
        />
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor="new-role">{t("admin.role")}</Label>
        <select id="new-role" className={select} value={form.role} onChange={set("role")}>
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {t(`admin.roles.${r}`)}
            </option>
          ))}
        </select>
      </div>
      {form.role === "responder" ? (
        <div className="grid gap-1.5">
          <Label htmlFor="new-agency">{t("admin.agency")}</Label>
          <select
            id="new-agency"
            className={select}
            required
            value={form.agency}
            onChange={set("agency")}
          >
            <option value="" />
            {AGENCIES.map((a) => (
              <option key={a} value={a}>
                {t(`admin.agencies.${a}`)}
              </option>
            ))}
          </select>
        </div>
      ) : null}
      {form.role === "hospital" ? (
        <div className="grid gap-1.5">
          <Label htmlFor="new-facility">{t("admin.facility")}</Label>
          <Input
            id="new-facility"
            size="sm"
            required
            value={form.facility_id}
            onChange={set("facility_id")}
          />
        </div>
      ) : null}
      <Button type="submit" size="sm" disabled={change.pending}>
        {t("admin.createUser")}
      </Button>
      <Status error={change.error} saved={change.saved} />
    </form>
  );
}

function UsersTab() {
  const { t } = useTranslation();
  const { data } = useList("users", () => api.GET("/admin/users"));
  return (
    <div className="flex flex-col gap-6">
      <NewUser />
      <Table
        caption={t("admin.tabs.users")}
        head={[
          t("admin.username"),
          t("admin.displayName"),
          t("admin.role"),
          t("admin.agency"),
          t("admin.phone"),
          t("admin.newPassword"),
          "",
        ]}
      >
        {data?.map((user) => (
          <UserRowView key={user.id} user={user} />
        ))}
      </Table>
    </div>
  );
}

/** Admin only: cameras, facilities, units and users; every change is audited (FR-ADM-001). */
export function AdminPage() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<Tab>("cameras");
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-display-sm font-bold text-balance">{t("admin.title")}</h1>
        <p className="text-muted-foreground">{t("admin.intro")}</p>
      </div>
      <div className="flex flex-wrap gap-2" role="group" aria-label={t("admin.title")}>
        {TABS.map((id) => (
          <Button
            key={id}
            size="sm"
            variant={tab === id ? "default" : "outline"}
            aria-pressed={tab === id}
            onClick={() => setTab(id)}
          >
            {t(`admin.tabs.${id}`)}
          </Button>
        ))}
      </div>
      <Card>
        <CardHeader>
          <h2 className="text-display-xs font-bold">{t(`admin.tabs.${tab}`)}</h2>
        </CardHeader>
        <CardContent>
          {tab === "cameras" ? <CamerasTab /> : null}
          {tab === "facilities" ? <FacilitiesTab /> : null}
          {tab === "units" ? <UnitsTab /> : null}
          {tab === "users" ? <UsersTab /> : null}
        </CardContent>
      </Card>
    </div>
  );
}

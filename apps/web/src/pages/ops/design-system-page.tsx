import { useState, type ReactNode } from "react";
import { PlusIcon } from "lucide-react";
import { useTranslation } from "react-i18next";

import { AiSourceTag } from "@/components/incident/ai-source-tag";
import { PriorityBadge } from "@/components/incident/priority-badge";
import { SimulatedLabel } from "@/components/incident/simulated-label";
import { StatusTimeline } from "@/components/incident/status-timeline";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";

const BRAND = [100, 200, 300, 400, 500, 600, 700, 800, 900] as const;
const SWATCH: Record<(typeof BRAND)[number], string> = {
  100: "bg-brand-100",
  200: "bg-brand-200",
  300: "bg-brand-300",
  400: "bg-brand-400",
  500: "bg-brand-500",
  600: "bg-brand-600",
  700: "bg-brand-700",
  800: "bg-brand-800",
  900: "bg-brand-900",
};

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-4">
      <h2 className="text-body-lg font-semibold text-ink">{title}</h2>
      <Card>{children}</Card>
    </section>
  );
}

/** Reference sheet of the design system: tokens and components as used by every surface. */
export function DesignSystemPage() {
  const { t } = useTranslation();
  const [choice, setChoice] = useState("a");
  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-2">
        <h1 className="text-display-xs font-semibold text-ink">{t("design.title")}</h1>
        <p className="text-body-md text-ink-muted">{t("design.intro")}</p>
        <ul className="mt-2 flex flex-wrap gap-2">
          {BRAND.map((step) => (
            <li key={step} className="flex flex-col items-center gap-1 text-body-xs">
              <span className={`size-12 rounded-2xl ${SWATCH[step]}`} />
              <bdi dir="ltr">{step}</bdi>
            </li>
          ))}
        </ul>
      </header>

      <Section title={t("design.buttons")}>
        <div className="flex flex-col gap-4">
          {(["lg", "default", "sm", "xs"] as const).map((size) => (
            <div key={size} className="flex flex-wrap items-center gap-3">
              <Button size={size}>
                <PlusIcon aria-hidden />
                {t("design.primary")}
              </Button>
              <Button size={size} variant="outline">
                {t("design.secondary")}
              </Button>
              <Button size={size} variant="secondary">
                {t("design.subtle")}
              </Button>
              <Button size={size} variant="ghost">
                {t("design.text")}
              </Button>
            </div>
          ))}
          <div className="flex flex-wrap items-center gap-3">
            <Button variant="success">{t("design.success")}</Button>
            <Button variant="success-solid">{t("design.success")}</Button>
            <Button variant="neutral">{t("design.neutral")}</Button>
            <Button variant="destructive">{t("design.error")}</Button>
            <Button disabled>{t("design.disabled")}</Button>
            <Button loading>{t("design.loading")}</Button>
            <Button size="icon" aria-label={t("design.primary")}>
              <PlusIcon aria-hidden />
            </Button>
          </div>
        </div>
      </Section>

      <Section title={t("design.inputs")}>
        <FieldGroup>
          <Field>
            <FieldLabel htmlFor="ds-email">{t("design.email")}</FieldLabel>
            <Input id="ds-email" type="email" dir="ltr" placeholder="name@example.dz" />
          </Field>
          <Field data-invalid>
            <FieldLabel htmlFor="ds-email-error">{t("design.email")}</FieldLabel>
            <Input id="ds-email-error" type="email" dir="ltr" aria-invalid defaultValue="name@" />
            <FieldError>{t("design.emailError")}</FieldError>
          </Field>
          <Field>
            <FieldLabel htmlFor="ds-message">{t("design.message")}</FieldLabel>
            <Textarea id="ds-message" />
          </Field>
          <Field>
            <FieldLabel htmlFor="ds-select">{t("design.choose")}</FieldLabel>
            <Select value={choice} onValueChange={setChoice}>
              <SelectTrigger id="ds-select" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent position="popper">
                <SelectItem value="a">{t("design.optionA")}</SelectItem>
                <SelectItem value="b">{t("design.optionB")}</SelectItem>
              </SelectContent>
            </Select>
          </Field>
        </FieldGroup>
      </Section>

      <Section title={t("design.controls")}>
        <div className="flex flex-col gap-5">
          <div className="flex items-center gap-3">
            <Checkbox id="ds-check" defaultChecked />
            <Label htmlFor="ds-check">{t("design.checkbox")}</Label>
          </div>
          <RadioGroup defaultValue="a" aria-label={t("design.choose")}>
            <div className="flex items-center gap-3">
              <RadioGroupItem id="ds-radio-a" value="a" />
              <Label htmlFor="ds-radio-a">{t("design.optionA")}</Label>
            </div>
            <div className="flex items-center gap-3">
              <RadioGroupItem id="ds-radio-b" value="b" />
              <Label htmlFor="ds-radio-b">{t("design.optionB")}</Label>
            </div>
          </RadioGroup>
          <div className="flex items-center gap-3">
            <Switch id="ds-switch" defaultChecked />
            <Label htmlFor="ds-switch">{t("design.toggle")}</Label>
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="ds-slider">{t("design.slider")}</Label>
            <Slider id="ds-slider" defaultValue={[67]} max={100} />
          </div>
          <Accordion type="single" collapsible defaultValue="why">
            <AccordionItem value="why">
              <AccordionTrigger>{t("design.accordionTitle")}</AccordionTrigger>
              <AccordionContent>{t("design.accordionBody")}</AccordionContent>
            </AccordionItem>
          </Accordion>
        </div>
      </Section>

      <Section title={t("design.badges")}>
        <div className="flex flex-wrap items-center gap-3">
          <PriorityBadge level={1} />
          <PriorityBadge level={2} />
          <PriorityBadge level={3} />
          <PriorityBadge level={4} />
          <AiSourceTag source={{ kind: "rule", id: "stalled_vehicle_live_lane" }} />
          <AiSourceTag source={{ kind: "model", id: "Qwen/Qwen3-VL-8B-Instruct-FP8" }} />
          <SimulatedLabel />
          <Badge>{t("status.verified")}</Badge>
        </div>
        <StatusTimeline
          current="en_route"
          steps={[
            { status: "candidate", at: "2026-10-30T08:00:00Z" },
            { status: "verified", at: "2026-10-30T08:01:00Z" },
            { status: "dispatched", at: "2026-10-30T08:02:00Z" },
            { status: "acknowledged", at: "2026-10-30T08:03:00Z" },
          ]}
        />
      </Section>

      <Section title={t("design.cards")}>
        <Card className="max-w-md">
          <CardHeader>
            <CardTitle>{t("design.cardTitle")}</CardTitle>
            <CardDescription>{t("design.cardBody")}</CardDescription>
          </CardHeader>
          <CardFooter>
            <Dialog>
              <DialogTrigger asChild>
                <Button>{t("design.openDialog")}</Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>{t("design.dialogTitle")}</DialogTitle>
                  <DialogDescription>{t("design.dialogBody")}</DialogDescription>
                </DialogHeader>
                <DialogFooter>
                  <Button>{t("design.confirm")}</Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </CardFooter>
        </Card>
      </Section>
    </div>
  );
}

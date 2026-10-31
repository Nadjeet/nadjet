import { useState, type FormEvent } from "react";
import { useNavigate } from "@tanstack/react-router";
import { CheckIcon } from "lucide-react";
import { useTranslation } from "react-i18next";

import { api } from "@/api";
import { LanguagePicker } from "@/components/brand/language-picker";
import { Logo } from "@/components/brand/logo";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader } from "@/components/ui/card";
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { authStore, homeFor } from "@/lib/auth-store";

type LoginError = "invalid" | "unavailable" | null;

/** Sign in, then land on the surface of the user's role (operator, responder, hospital). */
export function LoginPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<LoginError>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setPending(true);
    setError(null);
    try {
      const { data, response } = await api.POST("/auth/login", {
        body: { username: String(form.get("username")), password: String(form.get("password")) },
      });
      if (data) {
        authStore.setSession(data.access_token, data.user, data.expires_in);
        await navigate({ to: homeFor(data.user.role), replace: true });
      } else {
        setError(response.status === 401 ? "invalid" : "unavailable");
      }
    } catch {
      setError("unavailable");
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="grid min-h-dvh lg:grid-cols-2">
      <section
        aria-hidden
        className="relative hidden flex-col justify-end gap-6 overflow-hidden bg-[linear-gradient(112deg,#3568f5_7.6%,#80beff_95.5%)] p-12 text-white lg:flex"
      >
        <div className="pointer-events-none absolute -end-24 -top-24 size-96 rounded-full bg-white/10" />
        <div className="pointer-events-none absolute -start-32 bottom-24 size-80 rounded-full bg-white/5" />
        <h2 className="relative max-w-lg text-display-sm font-semibold text-balance">
          {t("login.heroTitle")}
        </h2>
        <p className="relative max-w-lg text-body-lg text-white/90">{t("login.heroBody")}</p>
        <ul className="relative flex flex-col gap-3 text-body-md">
          {(["point1", "point2", "point3"] as const).map((key) => (
            <li key={key} className="flex items-center gap-3">
              <span className="grid size-7 place-items-center rounded-full bg-white/20">
                <CheckIcon className="size-4" />
              </span>
              {t(`login.${key}`)}
            </li>
          ))}
        </ul>
      </section>
      <div className="flex flex-col justify-center gap-6 px-4 py-10 sm:px-10">
        <div className="mx-auto flex w-full max-w-md flex-col gap-6">
          <div className="flex items-center justify-between gap-3">
            <Logo className="h-12" />
            <LanguagePicker />
          </div>
          <Card>
            <CardHeader>
              <h1 className="text-body-lg font-semibold text-ink">{t("login.title")}</h1>
              <CardDescription>{t("login.subtitle")}</CardDescription>
            </CardHeader>
            <form onSubmit={submit} noValidate className="flex flex-col gap-5">
              <FieldGroup>
                <Field data-invalid={error === "invalid" || undefined}>
                  <FieldLabel htmlFor="username">{t("login.username")}</FieldLabel>
                  <Input
                    id="username"
                    name="username"
                    autoComplete="username"
                    autoCapitalize="none"
                    spellCheck={false}
                    required
                    aria-invalid={error === "invalid" || undefined}
                    dir="ltr"
                  />
                </Field>
                <Field data-invalid={error === "invalid" || undefined}>
                  <FieldLabel htmlFor="password">{t("login.password")}</FieldLabel>
                  <Input
                    id="password"
                    name="password"
                    type="password"
                    autoComplete="current-password"
                    required
                    aria-invalid={error === "invalid" || undefined}
                    dir="ltr"
                  />
                </Field>
              </FieldGroup>
              <div aria-live="assertive">
                {error ? <FieldError>{t(`login.${error}`)}</FieldError> : null}
              </div>
              <Button type="submit" size="lg" loading={pending} className="w-full">
                {t("login.submit")}
              </Button>
            </form>
          </Card>
        </div>
      </div>
    </main>
  );
}

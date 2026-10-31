import { MessageSquareIcon } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { useSmsGateway } from "@/lib/incident-queries";
import { smsUri } from "@/lib/sms-codes";

/**
 * "Send by SMS" (FR-RSP-004): opens the phone's SMS app addressed to the gateway with the
 * compact code ready, for a responder without mobile data. One tap, then send in the SMS app.
 */
export function SmsButton({
  body,
  size = "default",
}: {
  body: string | null;
  size?: "default" | "sm";
}) {
  const { t } = useTranslation();
  const gateway = useSmsGateway();
  const number = gateway.data;
  if (!body) return null;
  if (!number) {
    return gateway.isPending ? null : (
      <p className="text-body-xs text-ink-muted">{t("respond.sms.noNumber")}</p>
    );
  }
  return (
    <div className="flex flex-col gap-1">
      <Button asChild variant="outline" size={size} className="w-full">
        <a href={smsUri(number, body)}>
          <MessageSquareIcon aria-hidden />
          {t("respond.sms.send")}
        </a>
      </Button>
      <p className="text-body-xs text-ink-muted">
        {t("respond.sms.body")}{" "}
        <bdi dir="ltr" className="font-mono">
          {body}
        </bdi>
      </p>
    </div>
  );
}

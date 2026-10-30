import { useCallback, useEffect, useState } from "react";

type InstallEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
};

function isInstalled(): boolean {
  return window.matchMedia("(display-mode: standalone)").matches;
}

/** "Add to home screen": the browser's install prompt, kept until the user asks for it. */
export function useInstallPrompt(): {
  available: boolean;
  installed: boolean;
  install: () => void;
} {
  const [event, setEvent] = useState<InstallEvent | null>(null);
  const [installed, setInstalled] = useState(isInstalled);

  useEffect(() => {
    const onPrompt = (e: Event) => {
      e.preventDefault();
      setEvent(e as InstallEvent);
    };
    const onInstalled = () => {
      setEvent(null);
      setInstalled(true);
    };
    window.addEventListener("beforeinstallprompt", onPrompt);
    window.addEventListener("appinstalled", onInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", onPrompt);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  const install = useCallback(() => {
    if (!event) return;
    void event.prompt().then(() => setEvent(null));
  }, [event]);

  return { available: event !== null, installed, install };
}

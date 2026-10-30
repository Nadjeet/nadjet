import { useEffect } from "react";

const PUBLIC_MANIFEST = "/manifest-public.webmanifest";

/**
 * Installing from a public page must open the public pages, not the login page: swap the
 * manifest (start_url `/public`) while the public shell is shown. The build adds the link.
 */
export function usePublicManifest() {
  useEffect(() => {
    const link = document.querySelector<HTMLLinkElement>('link[rel="manifest"]');
    if (!link) return;
    const previous = link.getAttribute("href");
    link.setAttribute("href", PUBLIC_MANIFEST);
    return () => {
      if (previous) link.setAttribute("href", previous);
    };
  }, []);
}

import { useLayoutEffect } from "react";

/**
 * The operator console is dark, phone and public surfaces are light. The class goes on `<html>`
 * so portaled content (selects, dialogs) follows the same theme.
 */
export function useSurfaceTheme(theme: "dark" | "light") {
  // Layout effect: apply the theme before first paint so there is no light flash.
  useLayoutEffect(() => {
    const root = document.documentElement;
    root.classList.toggle("dark", theme === "dark");
    return () => root.classList.remove("dark");
  }, [theme]);
}

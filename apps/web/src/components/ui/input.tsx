import * as React from "react";

import { cn } from "@/lib/utils";

const field =
  "w-full min-w-0 rounded-[12px] border border-transparent bg-input px-4 text-body-sm text-ink transition-[border-color,box-shadow,background-color] outline-none placeholder:text-ink-subtle hover:border-border focus-visible:border-ring focus-visible:bg-card focus-visible:shadow-focus disabled:pointer-events-none disabled:opacity-50 aria-invalid:border-danger aria-invalid:bg-card aria-invalid:shadow-[0_0_0_4px_rgb(220_38_38/0.15)]";

type InputProps = Omit<React.ComponentProps<"input">, "size"> & { size?: "default" | "sm" };

/** Figma "Inputs": filled field, ring on focus, red when invalid (set `aria-invalid`). */
function Input({ className, type, size = "default", ...props }: InputProps) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(field, size === "sm" ? "h-10 text-body-sm" : "h-11", className)}
      {...props}
    />
  );
}

export { Input, field as fieldClasses };

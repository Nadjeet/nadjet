import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

// Teach tailwind-merge the design-system type scale (`text-body-md`, `text-display-lg`, …):
// without it these sizes are read as colours and silently drop `text-primary-foreground`.
const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      "font-size": [
        {
          text: [
            "display-xl",
            "display-lg",
            "display-md",
            "display-sm",
            "display-xs",
            "body-xl",
            "body-lg",
            "body-md",
            "body-sm",
            "body-xs",
          ],
        },
      ],
    },
  },
});

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

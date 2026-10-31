import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { Loader2Icon } from "lucide-react";
import { Slot } from "radix-ui";

import { cn } from "@/lib/utils";

/**
 * Figma "buttons" sheet (node 10:2097), 12 px radius, four sizes (48 / 44 / 40 / 36):
 * - `default` (Primary): blue-300 at rest, the blue gradient on hover and press;
 * - `gradient`: the gradient at rest, as the screens use it for the main action
 *   ("Dispatch Now", "Acknowledge Mission", "Start Transport to Hospital");
 * - `outline`: blue outline (the screens' "SMS Fallback");
 * - `success` (Secondary): green outline, filled green on hover, darker when pressed;
 * - `secondary` (Tertiary): light fill, darker on hover (the purple of the sheet in brand blue);
 * - `neutral`: the slate buttons of the screens ("Reject", "Details");
 * - disabled: the sheet's grey for every variant.
 */
const buttonVariants = cva(
  "group/button inline-flex shrink-0 items-center justify-center gap-2 rounded-[12px] border border-transparent font-medium whitespace-nowrap transition-[background,color,box-shadow] outline-none select-none focus-visible:shadow-focus disabled:pointer-events-none disabled:border-transparent disabled:bg-none disabled:bg-button-disabled disabled:text-button-disabled-ink disabled:shadow-none aria-busy:cursor-progress [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default:
          "bg-brand-300 text-white hover:bg-[linear-gradient(112deg,#3568f5_7.6%,#80beff_95.5%)] active:bg-[linear-gradient(112deg,#3568f5_7.6%,#80beff_95.5%)] active:brightness-95",
        gradient:
          "bg-[linear-gradient(112deg,#3568f5_7.6%,#80beff_95.5%)] text-white shadow-[0_8px_20px_-8px_rgb(53_104_245/0.6)] hover:shadow-[0_10px_24px_-8px_rgb(53_104_245/0.75)] active:brightness-95",
        outline: "border-brand-500 bg-card text-brand-500 hover:bg-brand-50 active:bg-brand-100/50",
        success:
          "border-success bg-card text-success hover:bg-success hover:text-white active:bg-success-strong active:text-white",
        "success-solid": "bg-success-strong text-white hover:bg-success active:bg-[#15803d]",
        secondary: "bg-brand-50 text-brand-indigo hover:bg-brand-100/60 active:bg-brand-100/80",
        neutral:
          "bg-surface-strong text-ink-body hover:bg-line active:bg-[#cbd5e1] [&_svg]:text-ink-muted",
        ghost: "text-brand-500 hover:bg-brand-50 active:bg-brand-100/50",
        destructive: "bg-danger text-white hover:bg-danger-strong active:bg-[#be123c]",
        link: "rounded-sm text-brand-500 underline-offset-4 hover:underline",
      },
      size: {
        lg: "h-12 px-6 text-body-sm",
        default: "h-11 px-5 text-body-sm",
        sm: "h-10 px-4 text-body-sm",
        xs: "h-9 px-3 text-body-xs",
        icon: "size-11",
        "icon-lg": "size-12",
        "icon-sm": "size-10",
        "icon-xs": "size-9",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

type ButtonProps = React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean;
    /** Shows a spinner, disables the button and sets aria-busy. */
    loading?: boolean;
  };

function Button({
  className,
  variant = "default",
  size = "default",
  asChild = false,
  loading = false,
  disabled,
  children,
  ...props
}: ButtonProps) {
  const classes = cn(buttonVariants({ variant, size, className }));
  if (asChild) {
    return (
      <Slot.Root
        data-slot="button"
        data-variant={variant}
        data-size={size}
        className={classes}
        {...props}
      >
        {children}
      </Slot.Root>
    );
  }
  return (
    <button
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={classes}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...props}
    >
      {loading ? <Loader2Icon aria-hidden className="animate-spin" /> : null}
      {children}
    </button>
  );
}

export { Button, buttonVariants };
export type { ButtonProps };

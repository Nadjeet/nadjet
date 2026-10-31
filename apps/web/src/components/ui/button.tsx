import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { Loader2Icon } from "lucide-react";
import { Slot } from "radix-ui";

import { cn } from "@/lib/utils";

/**
 * Figma "buttons": 12 px radius, Primary (blue gradient), Secondary (green outline, filled on
 * hover), Tertiary (light blue), disabled in grey; four sizes. The gradient ends on #0f7ae8
 * instead of brand-200 so white labels stay at WCAG AA (TD-54).
 */
const buttonVariants = cva(
  "group/button inline-flex shrink-0 items-center justify-center gap-2 rounded-[12px] border border-transparent font-medium whitespace-nowrap transition-[background,color,box-shadow,filter] outline-none select-none focus-visible:shadow-focus disabled:pointer-events-none disabled:border-transparent disabled:bg-none disabled:bg-surface-strong disabled:text-ink-subtle aria-busy:cursor-progress [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default:
          "bg-[linear-gradient(129deg,#3568f5_8%,#0f7ae8_95%)] text-white shadow-[0_6px_16px_-6px_rgb(53_104_245/0.55)] hover:brightness-95 active:brightness-90",
        outline:
          "border-primary bg-card text-primary hover:bg-accent active:bg-[color-mix(in_oklab,var(--accent),var(--primary)_10%)]",
        secondary:
          "bg-accent text-primary hover:bg-[color-mix(in_oklab,var(--accent),var(--primary)_10%)] active:bg-[color-mix(in_oklab,var(--accent),var(--primary)_18%)]",
        neutral:
          "border-border bg-surface-soft text-ink-body hover:bg-surface-strong active:bg-[color-mix(in_oklab,var(--color-surface-strong),black_5%)]",
        ghost: "text-primary hover:bg-accent active:bg-secondary",
        destructive:
          "bg-danger text-white hover:bg-[color-mix(in_oklab,var(--color-danger),black_14%)] active:bg-[color-mix(in_oklab,var(--color-danger),black_26%)]",
        success:
          "border-success bg-card text-success hover:bg-success hover:text-white active:bg-[color-mix(in_oklab,var(--color-success),black_18%)] active:text-white",
        "success-solid":
          "bg-success text-white hover:bg-[color-mix(in_oklab,var(--color-success),black_14%)] active:bg-[color-mix(in_oklab,var(--color-success),black_26%)]",
        link: "rounded-sm text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-11 px-5 text-body-sm",
        lg: "h-12 px-6 text-body-md",
        sm: "h-10 px-4 text-body-sm",
        xs: "h-8 rounded-[10px] px-3 text-body-xs",
        icon: "size-11",
        "icon-lg": "size-12",
        "icon-sm": "size-10",
        "icon-xs": "size-8 rounded-[10px]",
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

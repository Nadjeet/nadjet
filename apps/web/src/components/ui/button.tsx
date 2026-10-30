import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { Loader2Icon } from "lucide-react";
import { Slot } from "radix-ui";

import { cn } from "@/lib/utils";

/**
 * Figma "Rounded Buttons": pill shape, Primary / Secondary (outline) / Subtle / Text, four sizes,
 * icon buttons, loading, success and error. The Figma purple is mapped to the brand blue.
 */
const buttonVariants = cva(
  "group/button inline-flex shrink-0 items-center justify-center gap-2 rounded-full border border-transparent font-medium whitespace-nowrap transition-colors outline-none select-none focus-visible:shadow-focus disabled:pointer-events-none disabled:opacity-50 aria-busy:cursor-progress [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default:
          "bg-primary text-primary-foreground hover:bg-[color-mix(in_oklab,var(--primary),black_22%)] active:bg-[color-mix(in_oklab,var(--primary),black_38%)]",
        outline: "border-primary bg-transparent text-primary hover:bg-accent active:bg-secondary",
        secondary:
          "bg-accent text-accent-foreground hover:bg-[color-mix(in_oklab,var(--accent),var(--foreground)_8%)] active:bg-[color-mix(in_oklab,var(--accent),var(--foreground)_14%)]",
        ghost: "text-primary hover:bg-accent active:bg-secondary",
        destructive:
          "bg-danger text-white hover:bg-[color-mix(in_oklab,var(--color-danger),black_18%)] active:bg-[color-mix(in_oklab,var(--color-danger),black_32%)]",
        success:
          "bg-success text-white hover:bg-[color-mix(in_oklab,var(--color-success),black_18%)] active:bg-[color-mix(in_oklab,var(--color-success),black_32%)]",
        link: "rounded-sm text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-11 px-6 text-body-md",
        lg: "h-12 px-7 text-body-md",
        sm: "h-10 px-5 text-body-sm",
        xs: "h-9 px-4 text-body-xs",
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

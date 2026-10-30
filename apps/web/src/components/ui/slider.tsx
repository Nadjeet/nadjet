import * as React from "react";
import { Slider as SliderPrimitive } from "radix-ui";

import { cn } from "@/lib/utils";

/** Figma "Secondary Inputs / Sliders": gradient fill and a ringed thumb. */
function Slider({
  className,
  defaultValue,
  value,
  ...props
}: React.ComponentProps<typeof SliderPrimitive.Root>) {
  const thumbs = React.useMemo(
    () => (Array.isArray(value) ? value : Array.isArray(defaultValue) ? defaultValue : [0]),
    [value, defaultValue],
  );
  return (
    <SliderPrimitive.Root
      data-slot="slider"
      defaultValue={defaultValue}
      value={value}
      className={cn(
        "relative flex w-full touch-none items-center py-2 select-none data-[disabled]:opacity-50",
        className,
      )}
      {...props}
    >
      <SliderPrimitive.Track
        data-slot="slider-track"
        className="relative h-2 w-full grow overflow-hidden rounded-full bg-muted"
      >
        <SliderPrimitive.Range
          data-slot="slider-range"
          className="absolute h-full bg-gradient-to-r from-brand-300 to-primary rtl:bg-gradient-to-l"
        />
      </SliderPrimitive.Track>
      {thumbs.map((_, index) => (
        <SliderPrimitive.Thumb
          key={index}
          data-slot="slider-thumb"
          className="block size-6 rounded-full border-2 border-primary bg-background shadow-sm transition-shadow outline-none focus-visible:shadow-focus"
        />
      ))}
    </SliderPrimitive.Root>
  );
}

export { Slider };

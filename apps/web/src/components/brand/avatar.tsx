import avatarUrl from "@/assets/brand/avatar.png";
import { cn } from "@/lib/utils";

/**
 * Figma avatar: the designer's illustration on the amber `#ffb31f` disc. The same picture for
 * every user (no photos are stored: privacy by design).
 */
export function Avatar({ className }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={cn(
        "relative size-10 shrink-0 overflow-hidden rounded-full bg-[#ffb31f]",
        className,
      )}
    >
      <img
        src={avatarUrl}
        alt=""
        className="absolute -inset-x-[40%] -top-[35%] -bottom-[45%] size-[180%] max-w-none object-contain"
      />
    </span>
  );
}

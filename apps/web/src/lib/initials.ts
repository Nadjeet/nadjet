/** Initials of a display name for the avatar (no photos are stored: privacy by design). */
export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const letters = parts.length > 1 ? `${parts[0]![0]}${parts.at(-1)![0]}` : name.slice(0, 2);
  return letters.toUpperCase();
}

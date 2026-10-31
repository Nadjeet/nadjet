import type { Map as MapLibreMap } from "maplibre-gl";

import pinUrl from "./assets/pin.svg";
import unitUrl from "./assets/unit.svg";

/**
 * Map icons from the Figma map (TD-55): the red drop pin and the blue navigation marker are the
 * designer's SVGs; the hospital tile is the Figma "briefcase-medical" tile (brand-100 square).
 * Icons are rasterised at twice their size for sharp rendering on high-density screens.
 */
const HOSPITAL_SVG = `<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32">
<rect x="1" y="1" width="30" height="30" rx="8" fill="#aad4ff" stroke="#ffffff" stroke-width="2"/>
<g fill="none" stroke="#007dfe" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" transform="translate(7 7)">
<path d="M12 11h4M14 9v4M2 6.5h14v9H2zM6 6.5V4.5a1.5 1.5 0 0 1 1.5-1.5h3A1.5 1.5 0 0 1 12 4.5v2"/></g></svg>`;

const PLACE_SVG = `<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 22 22">
<circle cx="11" cy="11" r="9" fill="#ffffff" stroke="#3568f5" stroke-width="4"/></svg>`;

export const ICONS = {
  pin: { url: pinUrl, width: 30, height: 30 },
  unit: { url: unitUrl, width: 54, height: 54 },
  hospital: {
    url: `data:image/svg+xml;utf8,${encodeURIComponent(HOSPITAL_SVG)}`,
    width: 32,
    height: 32,
  },
  place: { url: `data:image/svg+xml;utf8,${encodeURIComponent(PLACE_SVG)}`, width: 22, height: 22 },
} as const;

export type IconName = keyof typeof ICONS;

const SCALE = 2;
const cache = new Map<IconName, Promise<ImageData>>();

function rasterise(name: IconName): Promise<ImageData> {
  const known = cache.get(name);
  if (known) return known;
  const { url, width, height } = ICONS[name];
  const promise = new Promise<ImageData>((resolve, reject) => {
    const image = new Image(width * SCALE, height * SCALE);
    image.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = width * SCALE;
      canvas.height = height * SCALE;
      const context = canvas.getContext("2d");
      if (!context) return reject(new Error("2D canvas unavailable"));
      context.drawImage(image, 0, 0, canvas.width, canvas.height);
      resolve(context.getImageData(0, 0, canvas.width, canvas.height));
    };
    image.onerror = () => reject(new Error(`Map icon ${name} failed to load`));
    image.src = url;
  });
  cache.set(name, promise);
  return promise;
}

/** Register the icons on a map (again after a style swap: images live in the style). */
export async function addIcons(map: MapLibreMap, names: IconName[]): Promise<void> {
  await Promise.all(
    names.map(async (name) => {
      const id = `nadjet-${name}`;
      const data = await rasterise(name);
      if (!map.hasImage(id)) map.addImage(id, data, { pixelRatio: SCALE });
    }),
  );
}

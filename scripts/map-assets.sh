#!/usr/bin/env bash
# Fetch the self-hosted map fonts and sprites (Protomaps basemaps-assets, OFL/BSD) into
# apps/web/public/map (git-ignored) so the basemap needs no external host at runtime.
set -euo pipefail
cd "$(dirname "$0")/.."

ASSETS_REF="028c18f713baecad011301ff7a69acc39bcc2ae7"
DEST="apps/web/public/map"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

curl -fsSL "https://github.com/protomaps/basemaps-assets/archive/${ASSETS_REF}.tar.gz" | tar -xz -C "$tmp"
src="$tmp/basemaps-assets-${ASSETS_REF}"

rm -rf "$DEST"
mkdir -p "$DEST/fonts" "$DEST/sprites"
for font in "Noto Sans Regular" "Noto Sans Medium" "Noto Sans Italic"; do
  cp -R "$src/fonts/$font" "$DEST/fonts/"
done
cp "$src"/sprites/v4/light* "$DEST/sprites/"
echo "Map assets ready in $DEST"

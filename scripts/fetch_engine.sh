#!/usr/bin/env bash
# Download a prebuilt stable-diffusion.cpp release (sd-server + sd-cli) into engine/bin.
# Usage: scripts/fetch_engine.sh [release-tag]   (default: latest)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$ROOT/engine/bin"
TAG="${1:-latest}"
REPO="leejet/stable-diffusion.cpp"

if [[ "$TAG" == "latest" ]]; then
  API="https://api.github.com/repos/$REPO/releases/latest"
else
  API="https://api.github.com/repos/$REPO/releases/tags/$TAG"
fi

case "$(uname -s)-$(uname -m)" in
  Darwin-arm64|Darwin-x86_64) PATTERN='Darwin.*arm64' ;;
  Linux-x86_64) PATTERN='ubuntu.*(cuda|vulkan|avx2)' ;;   # pick one; CUDA if you have an NVIDIA GPU
  *) echo "unsupported platform $(uname -s)-$(uname -m); build from source: https://github.com/$REPO" >&2; exit 1 ;;
esac

echo "Resolving $REPO release ($TAG)…"
JSON="$(curl -fsSL "$API")"
URL="$(printf '%s' "$JSON" | python3 -c "
import json,re,sys
d=json.load(sys.stdin)
pat=re.compile(sys.argv[1])
assets=[a for a in d['assets'] if pat.search(a['name']) and a['name'].endswith('.zip')]
if not assets: sys.exit('no matching asset; available: '+', '.join(a['name'] for a in d['assets']))
print(assets[0]['browser_download_url'])
" "$PATTERN")"
TAGNAME="$(printf '%s' "$JSON" | python3 -c "import json,sys; print(json.load(sys.stdin)['tag_name'])")"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
echo "Downloading $URL"
curl -fL --progress-bar -o "$TMP/sd.zip" "$URL"
unzip -q -o "$TMP/sd.zip" -d "$TMP/sd"

mkdir -p "$DEST"
find "$TMP/sd" -type f \( -name 'sd-server*' -o -name 'sd-cli*' -o -name '*.dylib' -o -name '*.so' -o -name '*.dll' \) -exec cp {} "$DEST/" \;
chmod +x "$DEST"/sd-server* "$DEST"/sd-cli* 2>/dev/null || true
echo "$TAGNAME" > "$DEST/VERSION"

# macOS: the binaries are unsigned; clear the quarantine flag so Gatekeeper does not block them.
if [[ "$(uname -s)" == "Darwin" ]]; then
  xattr -dr com.apple.quarantine "$DEST" 2>/dev/null || true
fi

echo "Installed $(ls "$DEST" | tr '\n' ' ') ($TAGNAME) into engine/bin"

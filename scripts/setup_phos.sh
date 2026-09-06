#!/usr/bin/env bash
# Holt Phos beim gepinnten Commit und spielt den Multi-Seat-Patch ein.
# Phos ist MIT-lizenziert (github.com/Ant3iros/Phos) und wird bewusst NICHT
# in dieses Repo vendored — wir halten nur den Patch.
set -euo pipefail

PHOS_REPO="https://github.com/Ant3iros/Phos.git"
PHOS_COMMIT="f0aaa4b746b38f3ee187171d57934e832340fbcb"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${PHOS_DIR:-$ROOT/vendor/phos}"
PATCH="$ROOT/patches/0001-multiseat.patch"

if [ -d "$DEST/.git" ]; then
  echo "==> $DEST existiert bereits. Setze auf $PHOS_COMMIT zurueck."
  git -C "$DEST" checkout -- . 2>/dev/null || true
  git -C "$DEST" checkout "$PHOS_COMMIT" 2>/dev/null || {
      git -C "$DEST" fetch --depth 50 origin && git -C "$DEST" checkout "$PHOS_COMMIT"; }
else
  echo "==> Klone Phos nach $DEST"
  mkdir -p "$(dirname "$DEST")"
  git clone --filter=blob:none "$PHOS_REPO" "$DEST"
  git -C "$DEST" checkout "$PHOS_COMMIT"
fi

echo "==> Pruefe Patch"
git -C "$DEST" apply --check "$PATCH"
echo "==> Wende Multi-Seat-Patch an"
git -C "$DEST" apply "$PATCH"

echo "==> Python-Abhaengigkeiten"
python3 -m pip install -q -r "$DEST/backend/requirements.txt"

echo
echo "Fertig. Backend starten mit:"
echo "  cd $DEST/backend && PAX_HOST=127.0.0.1 python3 -m uvicorn app.main:app --port 8000"
echo
echo "WICHTIG: Phos hat keine Authentifizierung — nur an 127.0.0.1 binden."

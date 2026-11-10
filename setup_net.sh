#!/bin/sh
# Helper: reassemble the default network from its three Drive parts.
#   net_aa + net_ab + net_ac  ->  src/nn-18cd32e11a9c.nnue
# The parts are the files named net* on Google Drive (split to bypass the
# 50 MiB per-file download limit).  After running the network is unlinked,
# because it is only a local build input (src/*.nnue is git-ignored).
set -e
here=$(cd "$(dirname "$0")" && pwd)
[ -f "$here/src/nn-18cd32e11a9c.nnue" ] && { echo "net already present"; exit 0; }
cat "$here"/google_drive/net_aa "$here"/google_drive/net_ab "$here"/google_drive/net_ac \
    > "$here/src/nn-18cd32e11a9c.nnue"
echo "reassembled src/nn-18cd32e11a9c.nnue"

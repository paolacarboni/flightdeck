#!/usr/bin/env bash
# <xbar.title>cc-panel</xbar.title>
# <xbar.desc>Sessioni Claude attive e decisioni di oggi (cc-panel feed).</xbar.desc>
# <xbar.author>flightdeck</xbar.author>
# xbar parte con un PATH minimo: «Approfondisci» apre una fork di claude nel terminale.
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
SELF="$(readlink -f "${BASH_SOURCE[0]}" 2>/dev/null || python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "${BASH_SOURCE[0]}")"
exec "$(dirname "$(dirname "$SELF")")/bin/cc-panel" bar

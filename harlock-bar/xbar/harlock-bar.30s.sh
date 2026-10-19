#!/usr/bin/env bash
# <xbar.title>Arcadia</xbar.title>
# <xbar.desc>Countdown, main task del giorno, ticket in lavorazione e scadenze (focus-panel + cc-panel).</xbar.desc>
# <xbar.author>flightdeck</xbar.author>
# Il plugin è un symlink nella cartella di xbar: risale al file vero e chiama bin/harlock-bar accanto.
SELF="$(readlink -f "${BASH_SOURCE[0]}" 2>/dev/null || python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "${BASH_SOURCE[0]}")"
exec "$(dirname "$(dirname "$SELF")")/bin/harlock-bar"

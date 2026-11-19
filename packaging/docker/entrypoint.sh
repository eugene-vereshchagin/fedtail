#!/bin/sh
# The container's start: a profile not made yet gets a config that waits on every
# address inside the container (the port is published by `docker run -p`) and opens no
# browser; the rest of the options are written in with their explanations
# (--update-config). Then the web interface; arguments go to fedtail (--profile NAME…).
set -e
profile=default
prev=""
for a in "$@"; do
    case "$prev" in -p|--profile) profile="$a" ;; esac
    case "$a" in --profile=*) profile="${a#--profile=}" ;; esac
    prev="$a"
done
cfg="$XDG_CONFIG_HOME/fedtail/$profile/config.toml"
if [ ! -f "$cfg" ]; then
    mkdir -p "$(dirname "$cfg")"
    printf '[web]\nhost = "0.0.0.0"\nport = 8765\nopen_browser = false\n' > "$cfg"
    fedtail --profile "$profile" --update-config >/dev/null
fi
exec fedtail --ui web "$@"

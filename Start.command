#!/bin/sh
# macOS: double-click to start (Finder opens it in Terminal); the work is start.sh's
exec "$(dirname "$0")/start.sh" "$@"

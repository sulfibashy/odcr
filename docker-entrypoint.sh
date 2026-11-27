#!/bin/sh
# Both forms work: `docker run IMAGE odcr run ...` and `docker run IMAGE run ...`.
set -e
if [ "$#" -eq 0 ]; then
  exec odcr --help
fi
case "$1" in
  odcr) shift; exec odcr "$@" ;;
  sh|bash|python|python3|pip|git) exec "$@" ;;
  *) exec odcr "$@" ;;
esac

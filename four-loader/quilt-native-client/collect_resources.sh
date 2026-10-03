#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
out=four-loader/quilt-native-client/logs/client-2/postfailure-cgroup.txt
[[ ! -e "$out" ]] || exit 2
{
  date -u --iso-8601=seconds
  printf '\nProcess cgroup:\n'; cat /proc/self/cgroup
  printf '\nCgroup mount:\n'; grep ' - cgroup' /proc/self/mountinfo
  for name in memory.max memory.high memory.current memory.events; do
    printf '\n%s:\n' "$name"; cat "/sys/fs/cgroup/$name"
  done
  printf '\nProcessors:\n'; nproc
  printf '\nMemory summary:\n'; free -m
} > "$out"
cat "$out"

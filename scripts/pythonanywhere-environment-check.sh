#!/usr/bin/env bash
set -uo pipefail

usable=0
seen=" "

for candidate in /usr/bin/python3 /usr/bin/python3.* /usr/local/bin/python3 /usr/local/bin/python3.*; do
  [ -x "$candidate" ] || continue
  case "$(basename "$candidate")" in
    *-config) continue ;;
  esac
  resolved="$(readlink -f "$candidate" 2>/dev/null || printf '%s' "$candidate")"
  case "$seen" in
    *" $resolved "*) continue ;;
  esac
  seen="$seen$resolved "

  version="$("$candidate" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || true)"
  if [ -z "$version" ]; then
    echo "不可用  $candidate  （无法启动）"
    continue
  fi

  if "$candidate" -c 'import subprocess, _posixsubprocess' >/dev/null 2>&1; then
    if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
      echo "可用    $candidate  Python $version"
      usable=1
    else
      echo "版本低  $candidate  Python $version（需要至少 3.11）"
    fi
  else
    echo "损坏    $candidate  Python $version（缺少 subprocess/_posixsubprocess）"
  fi
done

if [ "$usable" -eq 0 ]; then
  echo
  echo "没有找到可用的 Python 3.11+。请把以上输出发给 PythonAnywhere 支持。" >&2
  exit 1
fi

echo
echo "使用可用版本重建独立环境，例如："
echo "  mkvirtualenv --python=/usr/bin/python3.11 doc-collab-env"

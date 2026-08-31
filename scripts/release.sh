#!/bin/zsh
set -euo pipefail

version="${1:-}"
if [[ ! "$version" =~ '^v[0-9]+\.[0-9]+\.[0-9]+([-.][0-9A-Za-z.-]+)?$' ]]; then
  echo "Usage: $0 v1.2.3" >&2
  exit 2
fi

project_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$project_root"

if [[ -n "$(git status --porcelain)" ]]; then
  echo "The working tree is not clean. Commit or stash changes first." >&2
  exit 1
fi
if [[ "$(git branch --show-current)" != "main" ]]; then
  echo "Releases must be created from the main branch." >&2
  exit 1
fi

git tag -a "$version" -m "Release $version"
git push origin "$version"
echo "Pushed $version. GitHub Actions will build and publish the release."

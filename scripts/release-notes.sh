#!/usr/bin/env bash
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

## Generates categorized Markdown release notes for a macro release (vX.Y.Z).
#
# Usage:
#   scripts/release-notes.sh [--version X.Y.Z] [--from <tag>] [--to <ref>]
#
#   --version  version being released (default: contents of VERSION)
#   --from     previous release tag (default: latest vX.Y.Z tag reachable from
#              --to, excluding v<version> itself)
#   --to       git ref being released (default: HEAD)
#
# Sections: Breaking Changes, Features, Fixes, Improvements, Chart Versions.
# Commits are classified by Conventional Commit type when present
# (feat/fix/perf/refactor/docs/ci/chore/..., `!` or `BREAKING CHANGE` = breaking)
# and by keywords otherwise (e.g. "Add ArgoCD setup" -> Features,
# "Resolve dashboard duplication" -> Fixes, "Deployment guide" -> Improvements).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

VERSION=""; FROM=""; TO="HEAD"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --version) VERSION="$2"; shift ;;
    --from) FROM="$2"; shift ;;
    --to) TO="$2"; shift ;;
    -h|--help) sed -n '17,30p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 1 ;;
  esac
  shift
done

[[ -n "$VERSION" ]] || VERSION="$(git show "${TO}:VERSION" 2>/dev/null | tr -d '[:space:]')"
[[ -n "$VERSION" ]] || { echo "cannot determine version (pass --version)" >&2; exit 1; }
TAG="v${VERSION}"

if [[ -z "$FROM" ]]; then
  FROM="$(git tag --merged "$TO" --list 'v[0-9]*.[0-9]*.[0-9]*' --sort=-v:refname \
          | grep -vxF "$TAG" | head -n1 || true)"
fi
RANGE="${FROM:+${FROM}..}${TO}"

REPO_URL=""
if [[ -n "${GITHUB_REPOSITORY:-}" ]]; then
  REPO_URL="${GITHUB_SERVER_URL:-https://github.com}/${GITHUB_REPOSITORY}"
else
  origin="$(git remote get-url origin 2>/dev/null || true)"
  if [[ "$origin" =~ github\.com[:/]([^/]+/[^/.]+) ]]; then
    REPO_URL="https://github.com/${BASH_REMATCH[1]}"
  fi
fi

# ---------------------------------------------------------------- commits
# Record format: sha \x1f subject \x1f body \x1e
classified="$(git log --no-merges --format='%H%x1f%s%x1f%b%x1e' "$RANGE" | awk -v RS=$'\x1e' -F $'\x1f' -v url="$REPO_URL" '
  function has(s, re) { return match(s, "(^|[^a-z])(" re ")([^a-z]|$)") }
  {
    sha = $1; gsub(/^[ \t\r\n]+/, "", sha)
    subj = $2; body = $3
    if (sha == "" || subj == "") next
    if (subj ~ /^chore\(release\): v[0-9]/) next   # release PR bump commits

    cat = ""; scope = ""; desc = subj; breaking = 0
    if (match(subj, /^[A-Za-z]+(\([^)]*\))?!?: /)) {
      head = substr(subj, 1, RLENGTH - 2); desc = substr(subj, RLENGTH + 1)
      if (head ~ /!$/) { breaking = 1; sub(/!$/, "", head) }
      if (match(head, /\(.*\)/)) { scope = substr(head, RSTART + 1, RLENGTH - 2); head = substr(head, 1, RSTART - 1) }
      type = tolower(head)
      if (type ~ /^(feat|feature)$/) cat = "features"
      else if (type ~ /^(fix|bugfix|hotfix)$/) cat = "fixes"
      else if (type == "revert") cat = "fixes"
      else cat = "improvements"
    }
    if (body ~ /BREAKING[ -]CHANGE/) breaking = 1

    if (cat == "") {
      s = tolower(subj)
      if (has(s, "fix|fixes|fixed|bug|bugs|hotfix|resolve|resolves|resolved|correct|corrects|regression|revert"))
        cat = "fixes"
      else if (has(s, "doc|docs|documentation|guide|readme|license|typo|lint|format|bump|refactor|cleanup|clean up|rename|test|tests|ci|chore|update|updates|upgrade|improve|improves|deprecate"))
        cat = "improvements"
      else if (has(s, "feat|feature|features|add|adds|added|new|introduce|introduces|support|supports|setup|set up|implement|implements|enable|enables|allow|allows|integration|automate"))
        cat = "features"
      else
        cat = "improvements"
    }
    if (breaking) cat = "breaking"

    desc = toupper(substr(desc, 1, 1)) substr(desc, 2)
    short = substr(sha, 1, 7)
    ref = (url != "") ? "[`" short "`](" url "/commit/" sha ")" : "`" short "`"
    line = "- " (scope != "" ? "**" scope ":** " : "") desc " (" ref ")"
    printf "%s\t%s\n", cat, line
  }')"

section() {  # $1 = category key, $2 = heading
  local lines
  lines="$(printf '%s\n' "$classified" | awk -F'\t' -v c="$1" '$1 == c { sub(/^[^\t]*\t/, ""); print }')"
  if [[ -n "$lines" ]]; then
    printf '### %s\n\n%s\n\n' "$2" "$lines"
  fi
}

count() { printf '%s\n' "$classified" | awk -F'\t' -v c="$1" '$1 == c' | grep -c . || true; }

# ---------------------------------------------------------------- charts
chart_version_at() {  # $1 = ref, $2 = chart dir name; empty if chart absent at ref
  { git show "$1:charts/$2/Chart.yaml" 2>/dev/null || true; } | awk '/^version:/ { print $2; exit }' | tr -d "\"'"
}
chart_rows=""; unchanged=0
while read -r chart; do
  [[ -n "$chart" ]] || continue
  new_v="$(chart_version_at "$TO" "$chart")"
  old_v=""; [[ -n "$FROM" ]] && old_v="$(chart_version_at "$FROM" "$chart")"
  if [[ -z "$old_v" ]]; then
    chart_rows+="| \`${chart}\` | — | \`${new_v}\` | 🆕 new |"$'\n'
  elif [[ "$old_v" != "$new_v" ]]; then
    chart_rows+="| \`${chart}\` | \`${old_v}\` | \`${new_v}\` | ⬆️ updated |"$'\n'
  else
    unchanged=$((unchanged + 1))
  fi
done < <(git ls-tree -d --name-only "${TO}:charts" 2>/dev/null | while read -r d; do
           git cat-file -e "${TO}:charts/${d}/Chart.yaml" 2>/dev/null && echo "$d"; done)

# ---------------------------------------------------------------- output
echo "## GDC IaC Foundations ${TAG}"
echo
printf 'Released %s' "$(date -u +%Y-%m-%d)"
# shellcheck disable=SC2016  # backticks are literal Markdown code spans
[[ -n "$FROM" ]] && printf ' · changes since `%s`' "$FROM"
echo
echo
echo "| ⚠️ Breaking | ✨ Features | 🐛 Fixes | 🔧 Improvements |"
echo "| :-: | :-: | :-: | :-: |"
echo "| $(count breaking) | $(count features) | $(count fixes) | $(count improvements) |"
echo

if [[ -z "$classified" ]]; then
  echo "_No changes since ${FROM:-the beginning}._"
  echo
fi
section breaking     "⚠️ Breaking Changes"
section features     "✨ Features"
section fixes        "🐛 Fixes"
section improvements "🔧 Improvements"

echo "### 📦 Chart Versions"
echo
if [[ -n "$chart_rows" ]]; then
  echo "| Chart | Previous | This release | |"
  echo "| :-- | :-- | :-- | :-- |"
  printf '%s' "$chart_rows"
  echo
  echo "_${unchanged} other chart(s) unchanged._"
else
  echo "_No chart version changes (${unchanged} chart(s) unchanged)._"
fi
echo
echo "### 📥 Air-gap installation"
echo
echo "Download \`gdc-iac-airgap-${TAG}.tar.gz\`, verify it with \`sha256sum -c gdc-iac-airgap-${TAG}.tar.gz.sha256\`,"
echo "then ingest it with \`scripts/ingest-airgap-bundle.sh\`. The SPDX SBOM is attached as \`gdc-iac-sbom.spdx.json\`."
if [[ -n "$REPO_URL" && -n "$FROM" ]]; then
  echo
  echo "**Full changelog:** ${REPO_URL}/compare/${FROM}...${TAG}"
fi

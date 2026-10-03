#!/usr/bin/env bash
# Keep Docs/gu-library-ops-qa-prod.md identical across the app repo (Gu-Library)
# and the worker repo (Gu-Library-Worker).
#
# Each repo edits its own copy. This script 3-way merges ours with the other
# repo's copy, using as base the newest version of the doc that BOTH histories
# contain (git blobs are content-addressed, so "same text" == "same blob id").
# --publish then writes the merged result into BOTH repos, which is what lets
# the next run find its base. A merge committed here but not (yet) pushed over
# records the other side's version it merged in an "Ops-Doc-Merged: <blob>"
# trailer, so the base is still found when the other side has moved on since.
#
# The same file lives in both repos; only the per-machine git config differs.
# One-time setup per machine (Mac -> other is the worker repo, Atomman -> app):
#   git remote add worker https://github.com/hoanghieu512/Gu-Library-Worker.git
#   git config opsdoc.remote worker
#   git config opsdoc.mirror /path/to/vault/gu-library-ops-qa-prod.md   # optional
#
# Usage:
#   scripts/sync-ops-doc.sh                # merge into the working tree; never commits or pushes
#   scripts/sync-ops-doc.sh --base <rev>   # same, with an explicit base (only when auto-detect fails)
#   scripts/sync-ops-doc.sh --publish      # commit here, push the same file to the other repo, mirror it
#   scripts/sync-ops-doc.sh --publish --local   # only commit the merge here (other side busy); publish later
#
# Exit codes (sync): 0 = merged cleanly / nothing to do, 1 = conflict markers left in the doc.
set -euo pipefail

DOC=Docs/gu-library-ops-qa-prod.md
BRANCH=main

die() { echo "sync-ops-doc: $*" >&2; exit 2; }
say() { echo "sync-ops-doc: $*"; }

cd "$(git rev-parse --show-toplevel)"
GIT_DIR=$(git rev-parse --absolute-git-dir)
STATE="$GIT_DIR/ops-doc-sync.state"

REMOTE=$(git config opsdoc.remote || true)
[ -n "$REMOTE" ] || die "no other repo configured; run: git config opsdoc.remote <remote-name>"
git remote get-url "$REMOTE" >/dev/null 2>&1 || die "remote '$REMOTE' does not exist (git remote add $REMOTE <url>)"
THEIRS_REF="$REMOTE/$BRANCH"

[ "$(git symbolic-ref --short HEAD 2>/dev/null)" = "$BRANCH" ] || die "run this on '$BRANCH'"

MODE=sync
BASE_ARG=""
LOCAL_ONLY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --publish) MODE=publish ;;
    --local) LOCAL_ONLY=1 ;;
    --base) shift; BASE_ARG=${1:-}; [ -n "$BASE_ARG" ] || die "--base needs a commit or blob id" ;;
    -h|--help) sed -n '2,28p' "$0"; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
  shift
done
[ -z "$LOCAL_ONLY" ] || [ "$MODE" = publish ] || die "--local only goes with --publish"

git fetch -q origin "$BRANCH"
git fetch -q "$REMOTE" "$BRANCH"
THEIRS=$(git rev-parse "$THEIRS_REF:$DOC")

# Versions of $DOC that ref $1's history contains, newest first: each commit's
# own blob, then the other side's blob it says it merged (Ops-Doc-Merged).
versions_on() {
  git log --format=%H "$1" -- "$DOC" | while read -r c; do
    git rev-parse -q --verify "$c:$DOC" 2>/dev/null || true
    git log -1 --format=%B "$c" | sed -n 's/^Ops-Doc-Merged: //p'
  done
}

sync() {
  [ "$(git rev-list --count "HEAD..origin/$BRANCH")" = 0 ] \
    || die "origin/$BRANCH has commits you don't have; git pull first"
  git diff --quiet HEAD -- "$DOC" \
    || die "$DOC has uncommitted changes; commit them first (or, if this is a finished merge, run --publish)"

  local ours base
  ours=$(git rev-parse "HEAD:$DOC")
  if [ "$ours" = "$THEIRS" ]; then
    rm -f "$STATE"
    say "already identical to $THEIRS_REF; nothing to do"
    return 0
  fi

  if [ -n "$BASE_ARG" ]; then
    base=$(git rev-parse -q --verify "$BASE_ARG:$DOC" 2>/dev/null || git rev-parse -q --verify "$BASE_ARG^{blob}" 2>/dev/null) \
      || die "--base $BASE_ARG: no such commit (with $DOC) or blob"
  else
    local theirs_versions b
    theirs_versions=$(versions_on "$THEIRS_REF")
    base=""
    for b in $(versions_on HEAD); do
      if printf '%s\n' "$theirs_versions" | grep -qx "$b"; then base=$b; break; fi
    done
    [ -n "$base" ] || die "no common version of $DOC in both histories; pass --base <rev> (the other repo's commit this copy was last merged from)"
  fi
  printf 'theirs=%s\ntheirs_commit=%s\n' "$THEIRS" "$(git rev-parse --short "$THEIRS_REF")" > "$STATE"

  if [ "$base" = "$THEIRS" ]; then
    say "no new changes from $REMOTE; run --publish to send yours there"
    return 0
  fi
  if [ "$base" = "$ours" ]; then
    git cat-file blob "$THEIRS" > "$DOC"
    say "fast-forwarded to $THEIRS_REF's version; review, then run --publish"
    return 0
  fi

  local tmp conflicts
  tmp=$(mktemp -d)
  git cat-file blob "$ours" > "$tmp/ours"
  git cat-file blob "$base" > "$tmp/base"
  git cat-file blob "$THEIRS" > "$tmp/theirs"
  if git merge-file -L "here" -L "base" -L "$REMOTE" "$tmp/ours" "$tmp/base" "$tmp/theirs"; then
    conflicts=0
  else
    conflicts=$?
  fi
  [ "$conflicts" -lt 128 ] || { rm -rf "$tmp"; die "git merge-file failed"; }
  cp "$tmp/ours" "$DOC"
  rm -rf "$tmp"

  if [ "$conflicts" = 0 ]; then
    say "merged cleanly (base ${base:0:10}); review the diff, then run --publish"
    return 0
  fi
  say "$conflicts conflict(s) left as <<<<<<< here / >>>>>>> $REMOTE markers in $DOC"
  say "resolve them, then run --publish"
  return 1
}

publish() {
  [ -f "$STATE" ] || die "run a sync first (without --publish)"
  grep -nE '^(<<<<<<<|=======|>>>>>>>)( |$)' "$DOC" && die "conflict markers still in $DOC"

  local merged_from there_short result here_repo msg
  merged_from=$(sed -n 's/^theirs=//p' "$STATE")
  there_short=$(sed -n 's/^theirs_commit=//p' "$STATE")
  result=$(git hash-object -w --path="$DOC" "$DOC")
  here_repo=$(basename "$(git remote get-url origin)" .git)
  msg=$(mktemp)

  if [ "$result" != "$(git rev-parse "HEAD:$DOC")" ]; then
    printf 'docs(ops): sync ops doc with %s@%s\n\nOps-Doc-Merged: %s\n' \
      "$REMOTE" "$there_short" "$merged_from" > "$msg"
    [ -z "${OPS_SYNC_TRAILER:-}" ] || printf '%s\n' "$OPS_SYNC_TRAILER" >> "$msg"
    git commit -q -F "$msg" -- "$DOC"
    say "committed here: $(git log -1 --format='%h %s')"
  fi

  if [ -n "$LOCAL_ONLY" ] || [ "$merged_from" != "$THEIRS" ]; then
    rm -f "$STATE" "$msg"
    [ -n "$LOCAL_ONLY" ] || say "$THEIRS_REF changed since your sync, so nothing was pushed"
    say "not published; later run a sync (it merges only what's new over there), then --publish"
    return 0
  fi

  if [ "$result" != "$THEIRS" ]; then
    # Commit the doc on top of the other repo's branch without a checkout of it.
    local idx mode tree commit
    idx="$GIT_DIR/ops-doc-sync.index"
    rm -f "$idx"
    mode=$(git ls-tree "$THEIRS_REF" -- "$DOC" | awk '{print $1}')
    GIT_INDEX_FILE="$idx" git read-tree "$THEIRS_REF"
    GIT_INDEX_FILE="$idx" git update-index --cacheinfo "${mode:-100644},$result,$DOC"
    tree=$(GIT_INDEX_FILE="$idx" git write-tree)
    rm -f "$idx"
    printf 'docs(ops): sync ops doc from %s@%s\n' "$here_repo" "$(git rev-parse --short HEAD)" > "$msg"
    [ -z "${OPS_SYNC_TRAILER:-}" ] || printf '\n%s\n' "$OPS_SYNC_TRAILER" >> "$msg"
    commit=$(git commit-tree "$tree" -p "$THEIRS_REF" -F "$msg")
    git push -q "$REMOTE" "$commit:refs/heads/$BRANCH" \
      || die "push to $REMOTE rejected (it moved?); git checkout -- $DOC is NOT needed, just sync again"
    git fetch -q "$REMOTE" "$BRANCH"
    say "pushed to $REMOTE/$BRANCH: $(git log -1 --format='%h %s' "$commit")"
  fi
  rm -f "$msg"

  # The other machine finds its next base in OUR origin, so the sync commit must get there.
  local ahead
  ahead=$(git rev-list --count "origin/$BRANCH..HEAD")
  if [ "$ahead" = 1 ] && [ "$(git log -1 --format=%s)" = "docs(ops): sync ops doc with $REMOTE@$there_short" ]; then
    git push -q origin "HEAD:$BRANCH"
    say "pushed to origin/$BRANCH"
  elif [ "$ahead" != 0 ]; then
    say "WARNING: $ahead unpushed commit(s) on $BRANCH; push them yourself, the other side can't see this sync until you do"
  fi

  local mirror
  mirror=$(git config opsdoc.mirror || true)
  if [ -n "$mirror" ]; then
    if [ -d "$(dirname "$mirror")" ]; then
      cp "$DOC" "$mirror"
      say "copied to $mirror"
    else
      say "WARNING: mirror folder $(dirname "$mirror") not found; skipped"
    fi
  fi
  rm -f "$STATE"
  say "done: $DOC is identical in both repos"
}

"$MODE"

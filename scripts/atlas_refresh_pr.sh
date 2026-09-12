#!/usr/bin/env bash
set -euo pipefail
: "${GH_TOKEN:?Repository-scoped writer token required}"
[ "${GITHUB_REPOSITORY:-}" = 'QuietWire-Civic-AI/.github' ] || exit 1
[ "$#" -gt 0 ] || exit 1
for path in "$@"; do
  case "$path" in atlas/public.json|profile/README.md) ;; *) exit 1;; esac
done
git diff --cached --quiet || { echo 'Pre-staged changes refused' >&2; exit 1; }
git add -- "$@"

if git diff --cached --quiet; then echo 'No material Atlas changes'; exit 0; fi
key=$(python3 - <<'PY'
import hashlib,subprocess
paths=subprocess.check_output(['git','diff','--cached','--name-only','-z']).decode().split('\0')
h=hashlib.sha256()
for path in sorted(p for p in paths if p):
    body=subprocess.check_output(['git','show',':'+path]).decode()
    lines=[s for s in body.splitlines() if '"observed_at":' not in s and not s.startswith('Metadata snapshot:')]
    h.update(path.encode()+b'\0'+'\n'.join(lines).encode()+b'\0')
print(h.hexdigest()[:20])
PY
)
branch="automation/repository-atlas-$key"
# At most one active Atlas PR. Do not overwrite a human-modified PR branch.
pending=$(gh pr list -R "$GITHUB_REPOSITORY" --state open --limit 100 --json headRefName --jq '[.[] | select(.headRefName | startswith("automation/repository-atlas-"))] | length')
if [ "$pending" != 0 ]; then echo 'Atlas review already pending; no additional PR created'; exit 0; fi
prior=$(gh pr list -R "$GITHUB_REPOSITORY" --state all --head "$branch" --json number --jq length)
if [ "$prior" != 0 ]; then echo 'Identical Atlas change already proposed; not reopening it'; exit 0; fi
base=$(gh repo view "$GITHUB_REPOSITORY" --json defaultBranchRef --jq .defaultBranchRef.name)
# The runner must still represent the default branch we read, not an arbitrary PR.
remote_sha=$(gh api "repos/$GITHUB_REPOSITORY/commits/$base" --jq .sha)
[ "$(git rev-parse HEAD)" = "$remote_sha" ] || { echo 'Default branch moved; rerun against current source' >&2; exit 1; }
git switch -c "$branch"
git config user.name 'QuietWire Atlas'
git config user.email 'atlas@users.noreply.github.com'
git commit -m 'chore(atlas): propose observed repository topology update'
gh auth setup-git
git push "https://github.com/$GITHUB_REPOSITORY.git" "HEAD:refs/heads/$branch"
gh pr create -R "$GITHUB_REPOSITORY" --base "$base" --head "$branch" \
  --title 'Atlas: review observed repository changes' \
  --body 'Generated navigation update. No project code executed, no deployments, no permission changes, no automatic lifecycle decisions. Missing old IDs stop collection. New repositories are unclassified until a steward reviews them. Semantic review dates are not refreshed by polling. Review visibility and public-safe projection before merging. This PR never auto-merges.'

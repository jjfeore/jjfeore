# Contribution graph painter

`paint.py` draws `HI FOLKS!` across the five text rows of GitHub's 53-by-7
contribution calendar. The workflow refreshes the design automatically as the
rolling calendar advances.

## Why the old painter produced a blob

The old defaults created 7,701 commits per repaint. Repeated force-pushes only
caused slices of those histories to be reflected on the contribution calendar,
leaving several overlapping partial designs.

GitHub does not document a 1,000-commit contribution-indexing guarantee. That
number is an estimate from the live failure, not a supported API limit. GitHub's
documented repository limits allow much larger Git pushes, but accepting Git
objects and rebuilding a profile contribution index are separate operations.

## Dark cells without oversized rewrites

GitHub uses four relative contribution levels rather than a linear
"commits divided by maximum" shade. On this account's unpolluted 2024 and 2025
calendars, 10 contributions was the first count rendered at the darkest level;
five contributions rendered at level 2. The painter uses 20 per cell so normal
changes in real activity do not put the artwork right on that boundary.

The design generates 1,309 commits above the fixed cleanup root (1,310
reachable in total):

- 1,300 user-authored paint commits;
- eight bot-authored component restore tips; and
- one bot-authored commit that joins the component histories into `main`.

The total history is larger than 750 commits, but no normal refresh rewrites all
of it. Each glyph has an independent history rooted at the same fixed cleanup
commit. A daily run replaces one component and rebuilds the small joining
commit. The current design's largest batch changes 484 commits (old
component, new component, old join, and new join), below the workflow's
750-changed-commit
guard.

The 750 value is consequently a **per-rewrite churn limit**, not a documented
GitHub display or indexing limit.

## Automatic monthly refresh

The workflow is scheduled daily at 08:13 UTC. During the first eight successful
runs of a month it refreshes one component per day against a date pinned to the
first of that month. It then does nothing until the next month.

Components move right-to-left: `!`, `s`, `k`, `l`, `o`, `f`, `i`, and `H`.
New dates lie to the right of the previous month's dates. Updating the right
side first leaves a temporary gap between old and new components; updating `H`
first would make new left-hand letters overlap old right-hand letters.

Each component tip is kept in a `paint/<component>` branch and is also a parent
of the default-branch tip. This keeps every paint commit reachable from `main`,
which GitHub requires for contribution credit, while allowing one component to
be replaced without changing the other eight histories.

There is no 24-hour sleep inside a job. GitHub-hosted jobs cannot run that long.
The daily schedule is the persistent state machine: branch tips record the
target month and a fingerprint of each component's pixels and intensity. The
next run resumes from there. Scheduled runs can be delayed by GitHub, so the
spacing is approximately 24 hours rather than exact.

To update the message or glyph shapes later, edit and push the painter normally. The
fingerprints make changed components stale automatically; a manual `repaint`
run can start the first component, and the daily schedule finishes the rest.
The joining commit preserves the current repository tree while component tips
continue restoring the fixed root tree. A design edit therefore does not need
another cleanup or a locally run history generator.

## One-time migration from the 7,700-commit history

After publishing this version of `paint.py`, the tests, and the workflow:

1. Open **Actions -> Repaint contribution graph -> Run workflow**.
2. Select `cleanup` once.
3. Leave the workflow alone. Each daily run removes one 750-commit legacy
   history batch. A 23-hour guard prevents accidental rapid reruns.
4. In roughly 11 daily cleanup runs, the workflow creates one bot-authored
   fixed root containing the repository's current files.
5. After the root has aged at least 24 hours, daily runs automatically build
   the eight paint components, right-to-left.

The migration takes roughly three weeks end-to-end but needs only the first
manual `cleanup` dispatch. It intentionally gives GitHub time to process each
bounded history change. The normal monthly refresh is then fully automatic.

Do not run `cleanup` again after component painting has begun: legacy cleanup
expects the old linear history, while the new design intentionally uses merge
parents. If the contribution calendar has not reflected a batch after 24 hours,
wait rather than dispatching repeated runs; GitHub says qualifying
contributions can take up to 24 hours to appear.

## Local checks

```bash
python3 -m unittest discover -s art -p 'test_*.py' -v
python3 art/paint.py --preview --end-date 2026-07-01
python3 art/paint.py --list-components --order repaint
```

GitHub CLI is not required. It can make watching workflow runs more convenient,
but the migration and recurring repaint both run entirely in GitHub Actions.

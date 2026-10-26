---
name: tracking-issue
description: Draft, plan and work through a GitHub tracking issue, split into native sub-issues, one at a time on a single branch and PR, with one commit per sub-issue, a summary comment on the issue, and a stop for review after each. Use whenever work splits into two or more logically related issues, including when you are the one proposing the split (draft the tracking issue if none exists), and when the user asks to plan or set up a tracking issue (turn it into sub-issues), says "start <tracking issue>", "next", "proceed with R<n> (#<n>)", "approved", or asks to finish one before merging.
---

# Tracking issue

A larger change is a **tracking issue** whose native sub-issues are the steps, done in order on **one branch** with **one draft PR** that closes them all. Each step is one commit, a comment on its issue, and then a **stop** for the user's review. The user drives the pace: never start the next sub-issue until they say so.

Any work that splits into two or more logically related issues goes through this skill, never several standalone `issue` flows. If there is no tracking issue yet, start with [Draft](#draft).

Drafting and planning create only issues; they never create a branch, a commit or a PR. Implementing is a separate call.

Find the repo with `gh repo view --json nameWithOwner --jq .nameWithOwner`, called `O/R` below.

The tracking issue's body is the user's, including one drafted here and approved by them. Never edit it without asking; add decisions and the branch name as comments.

## Modes

- **Draft** (the work has no tracking issue yet, for example after a plan in chat, or when an `issue` plan turns out to need several issues): see [Draft](#draft).
- **Plan** ("plan #18", "set up #18"): see [Plan](#plan).
- **Step** ("start #18", "next", "proceed with R4 (#12)"): see [Step](#step). Most calls are this.
- **Approve** ("approved", "looks good"): see [Approve](#approve).
- **Feedback** on a finished step: see [Feedback](#feedback).
- **Finish** ("do the before-merging steps"): see [Finish](#finish).

"Next" means the previous step is approved: do [Approve](#approve) first, then the Step.

## Draft

Input: work that splits into related issues and has no tracking issue on GitHub yet.

1. **Check** for an existing tracking issue or open issues that overlap the work (`gh issue list`). Name any that the work would close or supersede, and ask before reusing an existing tracking issue.
2. **Write the body**, titled `Tracking: <summary>`, with these sections:
   - **Goal**: the problem and the intended outcome;
   - **Decisions**: what the user has already settled, and why;
   - **Steps**: the proposed sub-issues in order, as `R<n> — <Area>: <summary>` with one or two lines each (they become real sub-issues in Plan);
   - **Out of scope**, and **related issues** (`Closes #<n>` for ones it replaces).
3. **Show the draft in chat and stop.** Create it only after the user approves: `gh issue create --title ... --body-file ...`. Apply their changes to the draft first.
4. Once created, the body is the user's. Continue with [Plan](#plan) on the new issue (the decisions in the body count as settled).

## Plan

Input: the tracking issue on GitHub (written by the user, or drafted with [Draft](#draft) and approved).

1. **Read** the tracking issue and all its comments (`gh issue view <n> --json body,comments`), then the code it touches. Check whether it already has sub-issues.
2. **Ask** about choices that belong to the user and are not settled (a backend change, a new dependency, removing behaviour). Record the decisions in a comment on the tracking issue.
3. Label: `gh label create <area> --force` (for example `frontend`), if the area has none.
4. One sub-issue per point, in implementation order, titled `<Area>: <imperative summary>`. Each body has these sections:
   - **Problem**, with `path:line` references and the commit they refer to;
   - **Proposed change**;
   - **Out of scope**;
   - **Done when**, with the acceptance and the verification commands.
5. Link each one: `gh api repos/O/R/issues/<tracking>/sub_issues -F sub_issue_id=<id>`, where `<id>` is the database id from `gh api repos/O/R/issues/<n> --jq .id`, not the number.
6. Comment on the tracking issue with the plan: the ordered list of sub-issues, how the work proceeds (one commit each, a stop after each), and the branch name written as ``the branch `<branch>` `` (Step finds the branch this way).
7. **Stop**, so the user can look over the issues. Do not create the branch.

Order the steps so that guardrails (lint, types) come first. Put a step that removes duplication after the step that changes the underlying mechanism. Put large file moves in the middle, after logic changes, so the diffs stay readable. If a plan's step is too big to review as one commit, split it.

## Step

1. **Locate and check state.**
   - Tracking issue: the one the user names, or the one whose PR is open for the current branch (`gh pr view --json body`, then its first `Closes #`).
   - Branch: named in a tracking issue comment (or its body). If it exists, check it out and `git pull` it. If not, this is the first step: `git switch -c <branch> origin/main` (after `git fetch`). **Only create the branch**: no empty commit, no push, no PR yet.
   - Sub-issues, in order: `gh api repos/O/R/issues/<tracking>/sub_issues --jq '.[] | "\(.number) \(.state) \(.title)"'`.
   - The step: the one the user named. Otherwise the first sub-issue without a `Done in <sha>` comment.
   - State check, so an interrupted session recovers: which sub-issues have a `Done in` comment, whether the PR exists, which of its boxes are ticked, whether any step is done but not approved (do [Approve](#approve) first if the user said "next").
   - Make sure the working tree is clean before starting.
2. **Read** the sub-issue body and **all** its comments: `gh issue view <n> --json body,comments`. The user's comments answer the body's open questions and override it. Also read the tracking issue's comments if the sub-issue points to them.
3. **Decide what is unclear.** If a choice belongs to the user and neither the issue nor its comments settle it, ask before implementing it. Otherwise make the choice and say so in the report.
4. **Implement** only what the issue covers.
   - Use the project skills where they fit.
   - Something found along the way that is out of scope becomes a new sub-issue (ask first), not a drive-by change. If a sub-issue needs rescoping, update the sub-issues and note it in a tracking issue comment.
   - A pure move or reformat goes in its own commit before the edits, so `git log --follow` and the review stay clean.
5. **Check**, by the paths changed (see the `commit` skill and CLAUDE.md):
   - Rust: `cargo fmt`, `cargo clippy --all-targets` (no warnings), `cargo test`.
   - Frontend: `deno task fmt:check`, `lint`, `test` and `build` from `frontend/`.
   - **Behaviour:** for UI changes, run both dev servers (`.claude/launch.json`) and use the pages in the browser pane. Test writes only on throwaway data created with curl for the purpose and deleted afterwards. **Never change existing groups, game days or loaded data.**
   - **Tests:** when the step adds tests, break the code they cover on purpose and confirm a test fails, then restore it.
   - **Refactors:** for one that should not change the output, compare before and after (rendered text, bundle sizes, generated files) rather than trusting the build.
   - Clean up anything temporary: instrumentation, throwaway data, scratch files.
6. **Commit**, one commit per sub-issue (plus any separate move or format commit). Stage by path.
   - The message is the repo's style: one lowercase past-tense line saying what changed, with no prefix, ending with the sub-issue's number: `... (#<n>)`. The separate move or format commit gets the same number.
   - End the message with the attribution trailer from the session instructions.
7. **Push** the branch (`git push -u origin <branch>` the first time).
8. **Open the draft PR if there is none yet** (`gh pr create --draft`), now that the branch has a real commit. Its body is:
   - one line on how the work proceeds;
   - a task list `- [ ] #<n> <short title>` per sub-issue;
   - `Closes #<tracking>` and `Closes #<n>` for each sub-issue;
   - the PR attribution line.
9. **Comment** on the sub-issue with `gh issue comment <n> --body-file ...`:
   - It starts `Done in <sha>.`. Check the posted comment contains the SHA; fix it with `gh api -X PATCH repos/O/R/issues/comments/<id> -f body=...` if not.
   - Then bullets: what changed and why, the decisions made (especially ones that differ from the issue), how it was verified (with numbers where there are some), what was **not** verified and why, and the docs and skills updated.
10. **Stop and report** in chat:
    - the commit and PR link;
    - what changed for the user, and what was checked;
    - what you could not check;
    - the issue comment link;
    - the next sub-issue's number and title, offered but **not started**. The box is ticked once the user approves this commit.

Keep CLAUDE.md and the project skills accurate in the same commit as the change that affects them.

## Feedback

When the user asks for changes to a step that is not yet approved, make them as `git commit --fixup <that step's sha>`. A fixup needs no number of its own: `fixup! <subject>` repeats the original one. Run the checks, push, and add a comment on the sub-issue naming the fixup's SHA. Use a plain follow-up commit instead if the user wants the review history kept; its subject also ends with the sub-issue's `(#<n>)`.

Changes asked for after a step is approved are a normal follow-up commit ending with the sub-issue's `(#<n>)`, not a fixup: that history is already squashed and pushed.

## Approve

When the user approves a step's commit (directly, or by saying "next"):

1. **Squash its fixups** now, if there are any `fixup!` commits for it. Only that commit and the ones after it are rewritten:
   ```
   BEFORE=$(git rev-parse 'HEAD^{tree}')
   GIT_SEQUENCE_EDITOR=: git rebase -i --autosquash <step-sha>^
   test "$(git rev-parse 'HEAD^{tree}')" = "$BEFORE"   # the final tree must be byte-identical
   git push --force-with-lease origin <branch>
   ```
   Skip this if there are no fixups. There is no backup branch: `git reflog` and the tree check are the safety net. If the check fails, `git reset --hard` back to `ORIG_HEAD` and report.
2. **Fix the SHA** in the sub-issue's `Done in <sha>` comment (and any fixup comments) with `gh api -X PATCH`, when the squash changed it. Only this issue's comments need it, since each approval is squashed at once; there is no mapping table.
3. **Tick the PR task list** item for the sub-issue: `- [ ]` becomes `- [x]`, through `gh pr edit --body-file`.
4. Then stop, or continue with the next Step if the user said "next".

## Finish

Do these when the user asks for the before-merging steps:

1. **Check every sub-issue is approved**: it has a `Done in` comment, its box is ticked (tick any left, after confirming with the user), and no `fixup!` commits remain (`git log origin/main..HEAD --grep '^fixup!'`; run [Approve](#approve) for any that do).
2. **Mark the PR ready:** `gh pr ready <pr>`. Then check `get_status` (the ccd_pr tools) for mergeability and CI.
3. **Stop.** The user merges, with a merge commit so `main` keeps one commit per issue. Do not merge unless they ask. Afterwards, point out the remote branch they may want to delete.

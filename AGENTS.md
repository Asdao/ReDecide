# Agent instructions

Before adding, editing, deleting, or reorganizing anything in this repository,
inspect what is already present and understand how it is currently used.

Required workflow:

1. Inspect the relevant directory and search for existing implementations,
   documentation, tests, data loaders, and configuration before creating a new
   file or feature.
2. Check the current working-tree status and diff. Preserve existing user
   changes, including changes unrelated to the current task.
3. Reuse or extend an existing implementation when it already covers the need;
   do not create duplicate scripts, modules, manifests, or documentation.
4. For data changes, inspect the current data layout and use the repository's
   locked manifest or verification workflow when one exists. Do not silently
   replace or regenerate shared data.
5. Make the smallest change that satisfies the request. Before editing, state
   any assumption that could materially change the result.
6. Run focused tests and relevant validation after editing. Report any checks
   that could not be run and why.

Use `rg`/`rg --files` for searches, preserve existing conventions, and update
documentation when a workflow or user-facing command changes.

## Required RE:DECIDE context

Before beginning RE:DECIDE work, read:

1. `Project_Context.md` for stable scope, architecture, contracts, and ownership.
2. The numbered role brief for the task owner.
3. `INTEGRATION_STATUS.md` for the current end-to-end repository state.
4. The `STATUS.md` inside the component being changed.

Component status files describe current operational truth, not a daily diary.
After material work, the component owner updates their own status file with the
implemented behavior, important paths, test commands/results, limitations,
blockers, and integration handoff. Do not edit another owner's status file.

Person 1 maintains `INTEGRATION_STATUS.md` after changes are merged and verified.
Do not report branch-local work there as integrated before it reaches the shared
integration branch or `main`.

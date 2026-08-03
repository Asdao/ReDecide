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

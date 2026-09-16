---
name: vm-harness-silent-stub-gaps
description: A Node vm harness with incomplete DOM stubs silently produces false-clean results via the code's own try/catch, not an error
metadata:
  type: feedback
---

When building a throwaway Node `vm` harness to actually execute a rendered
`<script>` block for review (this repo's admin-surface JS is a good example,
see [[new538_edit_user_modal_approved]]), an incomplete stub
(`document.createElement`, `element.remove()`, `window.location`, etc.) does
not always throw visibly — if the code under test wraps the call site in its
own `try { ... } catch (ex) { alert(...) }` (a very common pattern in this
codebase's fetch-handler functions), the missing-stub error is swallowed by
*that* catch block and the function just returns early having done nothing.
The harness then reports something like "dynamic option count: 0" that looks
like a real (and wrong) result, when it's actually "the function never got
that far."

**Why this matters:** a reviewer trusting the first harness run here would
have wrongly concluded the ai_agent-role dynamic-dropdown-option feature was
broken, when the actual bug was in the harness's `document` stub (missing
`createElement`), not the code being reviewed.

**How to apply:** before trusting any vm-harness result that shows "nothing
happened" or "count is 0" for a feature the diff claims to add, check first
whether the harness's stub actually implements everything the real DOM API
the code touches would need (`createElement`, `appendChild`, `remove`,
`setAttribute`, `.value` getter/setter, `location`, `addEventListener`) —
grep the code under test for every DOM method it calls and cross-check the
stub covers each one. A "silent no-op" result is exactly as suspicious as an
explicit thrown error and needs the same level of distrust.

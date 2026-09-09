"""Stage B: evidence from outside the application document.

A candidate's public repositories are the strongest corroboration available,
and consulting them is also the easiest place in this system to do harm. The
whole package is built around one rule:

    Unavailable evidence is not negative evidence.

A repository that could not be read is not a repository that does not exist. A
rate-limited request, a timeout, and a private repository all mean "we did not
establish this", and none of them means "the candidate was not truthful".

That rule is structural rather than advisory. Corroboration wraps an existing
assessment instead of editing it, and combines the two grades with `max`, so
there is no code path through this package by which an external result lowers
anything. The document-only grade stays visible next to the corroborated one.
"""

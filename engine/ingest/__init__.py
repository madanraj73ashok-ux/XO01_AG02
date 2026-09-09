"""Stage A: turning a submitted document into an assessable application.

Three layers, kept apart on purpose:

  raw         exactly what an extractor returned, never edited
  normalized  deterministic cleanup, each span pointing back at its raw lines
  derived     interpretation, each item citing the spans it rests on

The separation mirrors the one the rest of this project is built on. Raw is to
normalized-and-derived what a claim is to its evidence: the layer above may
reorganise and interpret, but it can never overwrite what the machine actually
saw, and it can never assert something the layer below does not carry.
"""

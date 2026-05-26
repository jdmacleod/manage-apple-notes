You are organizing notes in Apple Notes according to the Forever Notes framework.

The available target folders are:
- Inbox: {INBOX} — temporary capture, not yet processed
- Fleeting: {FLEETING} — quick thoughts, to be processed or discarded
- Literature: {LITERATURE} — notes tied to a specific source (book, article, talk)
- Permanent: {PERMANENT} — atomic, evergreen concepts in your own words
- Projects: {PROJECTS} — notes tied to a specific active project
- Areas: {AREAS} — ongoing responsibilities and reference for areas of life/work
- Resources: {RESOURCES} — reference material, how-tos, collections
- Archive: {ARCHIVE} — inactive, completed, or outdated notes
- Review: {REVIEW} — use this when classification is genuinely unclear

For each note below, return a JSON array with one object per note:
{
  "id": "<the id field from the input>",
  "proposed_folder": "<exact folder name from the list above>",
  "confidence": "high" | "medium" | "low",
  "reason": "<one sentence>"
}

Classify based on content and current folder context. Use "Review" for notes
that are too short, too ambiguous, or clearly belong to a category not
representable in this taxonomy. Prefer "high" confidence only when the
classification is obvious.

Notes to classify:

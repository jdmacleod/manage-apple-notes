You are organizing notes in Apple Notes according to the Forever Notes framework.
The taxonomy has two levels: a top-level category (the nature of the note) and
an optional subfolder (the subject domain).

Available top-level categories and their subfolders:

Inbox: {INBOX} — temporary capture, no subfolders
Fleeting: {FLEETING} — quick thoughts, no subfolders
Literature: {LITERATURE} — notes tied to a specific source (book, article, talk)
  Subfolders: {LITERATURE_SUBFOLDERS}
Permanent: {PERMANENT} — atomic, evergreen concepts in your own words
  Subfolders: {PERMANENT_SUBFOLDERS}
Projects: {PROJECTS} — notes tied to a specific active project
  Subfolders: {PROJECTS_SUBFOLDERS}
Areas: {AREAS} — ongoing responsibilities and reference for areas of life/work
  Subfolders: {AREAS_SUBFOLDERS}
Resources: {RESOURCES} — reference material, how-tos, collections
  Subfolders: {RESOURCES_SUBFOLDERS}
Archive: {ARCHIVE} — inactive, completed, or outdated notes
  Subfolders: {ARCHIVE_SUBFOLDERS}
Review: {REVIEW} — use when classification is genuinely unclear, no subfolders

For each note below, return a JSON array with one object per note:
{
  "id": "<the id field from the input>",
  "proposed_folder": "<exact top-level folder name from the list above>",
  "proposed_subfolder": "<exact subfolder name, or null if none applies>",
  "confidence": "high" | "medium" | "low",
  "reason": "<one sentence>"
}

Use null for proposed_subfolder when: no subfolders are defined for the target
category, or the note's theme doesn't clearly match any listed subfolder.
Use "Review" (with null subfolder) for notes that are too short, too ambiguous,
or clearly belong to a category not representable in this taxonomy.
Prefer "high" confidence only when the classification is obvious.

Notes to classify:

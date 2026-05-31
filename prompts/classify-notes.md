You are organizing notes in Apple Notes according to a configured folder taxonomy.
Folders are organized into hierarchical paths separated by "/".

Available folder paths (use the exact path shown in brackets, or the top-level folder name if no path applies):

{CATEGORY_LIST}

For each note below, return a JSON array with one object per note:
{
  "id": "<the id field from the input>",
  "proposed_folder_path": "<exact folder path, e.g. 'Resources/Programming/Python'>",
  "proposed_folder": "<first path component>",
  "proposed_subfolder": "<everything after the first '/', or null>",
  "confidence": "high" | "medium" | "low",
  "reason": "<one sentence>"
}

Use null for proposed_subfolder when the note belongs at the top-level folder only.
Use "{CATCHALL}" (with null proposed_subfolder) for notes that are too short, too ambiguous,
or clearly belong to a category not representable in this taxonomy.
Prefer "high" confidence only when the classification is obvious.

{RELOCATION_GUIDANCE}

Notes to classify:

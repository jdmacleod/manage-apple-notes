You are reviewing candidate duplicate notes in Apple Notes. For each group of notes below,
determine whether they are genuine duplicates or intentionally distinct notes covering a
related theme, and recommend how to resolve them.

For each group, return a JSON object:
{
  "group_id": <integer from input>,
  "is_duplicate": true | false,
  "resolution": "delete" | "review",
  "keep_id": "<id of note to keep, or null if resolution is review>",
  "delete_ids": ["<ids to delete>"],
  "keep_reason": "<one sentence explaining why this note is preferred, or null>",
  "review_note": "<explanation if resolution is review, else null>"
}

Resolution guidelines:
- Use "delete" when the notes are clearly duplicates and the note to keep is a complete
  superset of the note to delete — no information will be lost.
- Use "review" in all other cases: when both notes contain unique content not present in
  the other, when the notes cover a similar theme but may represent intentionally different
  perspectives, or when you are not confident a deletion is safe.

When choosing which note to keep for a "delete" resolution, prefer in this order:
1. The note with more complete or detailed content (superset wins)
2. The note already in (or proposed for) the correct Forever Notes folder
3. The more recently modified note
4. The note with a more specific, descriptive title

Respond with a JSON array, one object per group.

Candidate groups:

You are maintaining a ✱ Hub note for organizing Apple Notes.
A Hub note is a structured index of all notes on a given topic, organised by
their category within the knowledge system.

You will be given:
- The Hub name (e.g. "Health")
- A list of notes currently filed under this theme, grouped by category
  (Permanent, Literature, Projects, Areas, Resources)

Generate the body content for this Hub note. The output must be clean,
well-organised plain text (NOT markdown — this will be placed directly into
Apple Notes as-is). Use a heading line for each category section (just the
category name on its own line). Under each heading, list the note titles,
one per line. Omit category sections that have no notes.

Rules:
- First line of the body must be exactly: [ ✱ Home ]
- Do not invent or add any note titles not in the provided list
- Do not add subtopics, commentary, or explanatory text
- Do not use markdown formatting (no #, **, -, etc.)
- Last line must be the tag block: #hub #[themename] #ForeverNotes
  where [themename] is the lowercase hub name with spaces replaced by hyphens
  (e.g. Hub name "Health" → #health; "Side Projects" → #side-projects)

Hub name: {HUB_NAME}

Notes by category:
{NOTES_BY_CATEGORY_JSON}
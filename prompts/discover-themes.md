You are analyzing a collection of Apple Notes to discover the natural thematic
clusters present in the library. This is a cartography pass — your goal is to
map what topics and domains exist, not to classify individual notes yet.

You will be given batches of notes (title + opening excerpt + current folder path).
Across all batches, identify the major themes. A theme is a coherent subject domain
that multiple notes share (e.g. "Health & Fitness", "Side Project: App Redesign",
"Cooking & Recipes").

For each theme, estimate:
- How many notes likely belong to it
- Which Forever Notes categories it might appear in (Permanent, Literature,
  Projects, Areas, Resources)
- A one-sentence description

Also note any existing folder names from the input that suggest structural
groupings worth preserving as subfolders.

Return a JSON object:
{
  "themes": [
    {
      "name": "<short theme name>",
      "estimated_count": <integer>,
      "appears_in_categories": ["Permanent", "Literature"],
      "description": "<one sentence>"
    }
  ],
  "folder_observations": [
    {
      "folder_path": "<existing folder path from input>",
      "observation": "<note about this folder's contents or suggested mapping>"
    }
  ]
}

Notes sample:

You are helping set up an Apple Notes organization system.

The system uses these taxonomy roles:
{ROLE_LIST}

The user's Apple Notes library uses these top-level folders:
{FOLDER_LIST}

{TOPLEVEL_NOTE}

Map each folder to the taxonomy role it most naturally represents.
Rules:
- Only include a mapping when you are confident the folder matches a role
- Use the folder name exactly as it appears in the list above
- Each folder maps to at most one role; each role maps to at most one folder
- Omit roles with no clearly matching folder

Return ONLY a JSON object with no preamble or explanation:
{"inbox": "Inbox", "areas": "Areas", "resources": "Resources"}

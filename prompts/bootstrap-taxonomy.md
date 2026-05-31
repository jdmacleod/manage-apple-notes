You are helping set up an Apple Notes organization system.

The system uses these taxonomy roles:
- inbox: temporary capture — unprocessed notes waiting to be filed
- fleeting: quick, short-lived thoughts and scratch notes
- literature: notes tied to a specific source (book, article, talk, course)
- permanent: refined, evergreen notes in your own words on a lasting concept
- projects: notes for specific active projects you are currently working on
- areas: ongoing life or work responsibilities (health, finances, relationships, work areas)
- resources: reference material, how-tos, collections of useful information
- archive: inactive, completed, or outdated notes no longer in active use
- review: notes that need human attention before they can be properly filed

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

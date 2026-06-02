# PARA Method — Taxonomy Guide for Apple Notes

> **Purpose of this document:**  
> This guide explains the PARA method, offers two ready-to-use taxonomy designs
> (minimalist and expanded), and provides decision guidance to help you choose and
> configure the right structure for your situation. It is also used as reference
> material when Claude generates a `taxonomy.local.yaml` for this project.
>
> PARA was created by Tiago Forte. See the original documentation at
> [fortelabs.com/blog/para](https://fortelabs.com/blog/para/).

---

## What Is PARA?

PARA is a four-category system for organizing all digital information by
**actionability** — how actively you are working with something right now —
rather than by topic or subject matter.

The four categories are:

| Category | Definition | Ends? |
|----------|------------|-------|
| **Projects** | Short-term efforts with a defined outcome and a deadline | Yes |
| **Areas** | Ongoing responsibilities with a standard to maintain | No |
| **Resources** | Topics and interests you are accumulating for future use | No |
| **Archive** | Inactive items from the other three categories | — |

### The Most Important Distinction: Projects vs Areas

This is the distinction that changes behavior most. Most people mistake Areas
for Projects, producing a list of responsibilities that never shrinks and never
gets crossed off. PARA insists on the difference:

- **"Health"** is an Area — it has no end date, only a standard to maintain.
- **"Book appointment with cardiologist"** is a project — it has a clear
  outcome and will be finished.
- **"Finance"** is an Area.
- **"Consolidate pension accounts"** is a project.

A project must have both a **specific outcome** and an implicit or explicit
**deadline**. If either is missing, it is an Area (or a task within an Area,
managed in a task manager rather than a note system).

### Why Organize by Actionability?

Organizing by topic (the way most people learned in school) produces broad
categories like "Psychology" or "Business" that are too large to navigate
usefully. Organizing by actionability ensures that when you open your Projects
folder, everything in it demands attention and has a finish line. When a project
completes, it moves to Archive — the system stays current automatically.

---

## Compatibility with the Forever Notes Framework

PARA and the Forever Notes framework operate at different levels and are
complementary, not competing:

- **PARA** defines the top-level structure — the nature and lifecycle of a
  note's relationship to your current commitments.
- **Forever Notes** adds navigational infrastructure — the ✱ Home note, ✱ Hub
  notes, tags, and the heavy asterisk prefix for system notes.

You can use PARA as the folder taxonomy and layer Forever Notes structural
elements (strict mode) on top. The `forever_notes_mode` setting in
`settings.local.yaml` controls whether hub notes and tags are generated.

### Mapping PARA to the Broader Toolkit Taxonomy

The manage-apple-notes project's default taxonomy includes Zettelkasten-
influenced categories (Fleeting, Literature, Permanent) alongside PARA's four.
If you prefer pure PARA, these map as follows:

| This project's default | PARA equivalent |
|-----------------|-----------------|
| Inbox | Inbox (kept in both — universal staging area) |
| Fleeting | Inbox (merge — fleeting notes are unprocessed captures) |
| Literature | Resources / Learning & Reading |
| Permanent | Resources / Ideas & Thinking |
| Projects | Projects |
| Areas | Areas |
| Resources | Resources / Reference |
| Archive | Archive |
| Review | Archive or a flat Review folder (optional) |

Switching to pure PARA reduces top-level folders from nine to five, with
Resources carrying the differentiation internally via subfolders.

---

## Choosing Your Taxonomy

### Key Questions

Before choosing minimalist or expanded, consider:

1. **How many active projects do you typically have?**
   - 1–5 → minimalist (flat Projects folder is manageable)
   - 6–15 → expanded (per-project subfolders aid navigation)
   - 15+ → expanded, and consider whether some "projects" are actually Areas

2. **What is your primary capture type?**
   - Mostly reference and how-to material → flat Resources is fine
   - Heavy on ideas, reading notes, and half-formed thinking → Resources
     benefits from internal differentiation (see expanded set)
   - Mostly meeting notes and work tasks → consider a task manager alongside
     Apple Notes; PARA works best when notes are knowledge, not to-dos

3. **How much do you rely on search vs browsing?**
   - Trust search, title notes well → minimalist
   - Prefer visual navigation → expanded

4. **Are you migrating from chaos or starting fresh?**
   - Migrating → start with minimalist; split Resources later if needed
   - Starting fresh → either works; expanded gives more places to land notes
     consistently from the start

---

## Minimalist PARA Taxonomy

**Five top-level folders, nine folders total.** Primary navigation by search.
Projects stays flat; disciplined note titling replaces subfolder structure.

```
Inbox
Projects
Areas
  └── Work
  └── Health
  └── Finance & Household
  └── Personal
Resources
Archive
```

### Notes on the Minimalist Design

**Inbox** is a temporary staging area only. Notes should not stay here beyond
a regular processing pass (daily or a few times per week).

**Projects** is flat. With up to ~10 active projects, this works well if every
note title begins with the project name: `"Website Redesign — Kickoff Notes"`,
`"Website Redesign — Stakeholder Feedback"`. This makes search instant and
avoids the overhead of creating and retiring subfolders as projects turn over.

**Areas** has four subfolders representing the four major life domains most
knowledge workers maintain. Adjust to match your actual ongoing responsibilities.
A new Area subfolder should only be created when a domain has accumulated enough
notes that browsing the flat Areas folder becomes friction — 8 or more
notes on a distinct theme (matching the `min_notes_for_subfolder` threshold in `settings.example.yaml`).

**Resources** is intentionally flat. Everything that is not a project or area
lives here: reading notes, reference material, ideas, how-tos. Navigate by
search. This is the deliberate "good enough" concession that keeps the rest of
the system frictionless.

**Archive** is flat. Completed projects and retired areas move here without
renaming. The project or area name in the note title is sufficient for future
retrieval.

### When to Choose Minimalist

- You are migrating a large, disorganized library and want quick results
- You prefer a system that stays out of the way
- You have fewer than 8–10 active projects at any time
- Your Resources notes are predominantly reference material (not ideas or
  structured reading notes)
- You are comfortable relying on search for retrieval

---

## Expanded PARA Taxonomy

**Five top-level folders, ~20–30 folders total** (varying with active project
count). Per-project subfolders and a differentiated Resources layer.

```
Inbox

Projects
  └── [Project Name 1]
  └── [Project Name 2]
  └── [Project Name 3]
  └── ... (one subfolder per active project)

Areas
  └── Work
  └── Health & Wellbeing
  └── Finance
  └── Household
  └── Personal

Resources
  └── Ideas & Thinking
  └── Learning & Reading
  └── Reference

Archive
  └── Projects
  └── Areas
  └── Resources
```

### Notes on the Expanded Design

**Projects** gets one subfolder per active project. When a project completes,
its subfolder moves to `Archive/Projects`. This creates a visible record of
completed work and keeps the active Projects folder current. The churn is
intentional — a constantly-rotating Projects list is motivating and clarifying.

Project subfolders should be named simply and clearly: `"Home Renovation"`,
`"Q3 Marketing Campaign"`, `"Spanish Language Course"`. Avoid dates in the
subfolder name (dates belong in note titles); the Archive date is implicit in
when it was moved.

**Areas** has five subfolders. Compared to the minimalist set, Finance and Household
are separated (they accumulate different types of notes), and Personal is added
as a distinct domain. Add or remove Area subfolders to match your actual
ongoing responsibilities — there is no correct number.

**Resources** is split into three lanes:

- **Ideas & Thinking** — half-formed thoughts, hypotheses, observations, notes
  you expect to develop over time. These are closest to what the Zettelkasten
  tradition calls atomic or "permanent" notes. They tend to be written in your
  own words and not tied to a specific source.
- **Learning & Reading** — notes tied to a specific source: book summaries,
  course notes, article digests, highlights with commentary. These are closest
  to what the Zettelkasten tradition calls "literature notes". The source title
  or author should appear in the note title.
- **Reference** — stable how-to material, factual reference, saved procedures,
  templates. Notes you look things up in rather than develop over time.

**Archive** has three mirroring subfolders so retired items land somewhere
logical. Archive is not searched often — its primary purpose is to keep the
active folders clean while preserving material that might be useful later.

### When to Choose Expanded

- You have 8 or more active projects running simultaneously
- Your Resources notes span meaningfully different types (ideas, source-linked
  reading notes, and reference material)
- You prefer visual navigation alongside search
- You are starting fresh (rather than migrating) and want consistent structure
  from the beginning
- You intend to use Forever Notes strict mode, where Hub notes aggregate
  content across subfolders — the expanded Resources subfolders give Hubs
  more meaningful structure to index

---

## Guidance for Claude: Generating `taxonomy.local.yaml`

When using Claude to generate or populate `taxonomy.local.yaml` based on this
document, provide the following as context alongside this file:

1. **Which taxonomy to use** — minimalist or expanded, or a custom variant.
2. **Your actual folder names** — Apple Notes folder names cannot contain
   certain special characters. Keep them short and clear.
3. **Your active projects** — for the expanded set, list current project names
   so Claude can pre-populate the Projects subfolders list.
4. **Your Areas** — confirm or adjust the four/five default Area subfolders to
   match your actual ongoing responsibilities.
5. **Your operating mode** — `loose` (folders only) or `strict` (folders plus
   Forever Notes Hub notes and tags).

### Sample Prompt for Claude

```
Using the PARA taxonomy guidance in docs/para-method.md, generate a
taxonomy.local.yaml for my Apple Notes library. I want the [minimalist /
expanded] set. My active projects are: [list]. My main areas of responsibility
are: [list]. I am using [loose / strict] mode. My iCloud Notes account is the
primary account.
```

### What Claude Will Generate

Claude will produce a `taxonomy.local.yaml` following the schema in
`config/taxonomy.zettelkasten.yaml`, with:

- Top-level category folder names filled in
- Subfolders populated based on your inputs
- For strict mode: `hub_title` and `hub_tag` values auto-derived or specified
- A comment block at the top summarizing the taxonomy choices made

The generated file should be reviewed before use. Pay particular attention to:
- Folder names — must match exactly what exists or will be created in Apple Notes
- Project subfolders — should only list currently active projects
- Area subfolders — should reflect actual ongoing responsibilities, not aspirations

---

## Quick Reference: PARA in One Table

| Folder | Contains | Lifecycle | Subfolders |
|--------|----------|-----------|------------|
| Inbox | Unprocessed captures | Transient — process regularly | None |
| Projects | Notes for active, bounded efforts | Transient — retire to Archive on completion | One per project (expanded) or none (minimalist) |
| Areas | Notes for ongoing responsibilities | Permanent — never "done" | One per life domain |
| Resources | Knowledge, ideas, reference material | Permanent — accumulates over time | None (minimalist) or three-lane split (expanded) |
| Archive | Inactive items from all other categories | Permanent — rarely accessed | Mirroring subfolders (expanded) or none (minimalist) |

---

## Customisation

Both PARA designs above are starting points. Copy `config/taxonomy.para.yaml` to
`taxonomy.local.yaml`, rename folders to match your Apple Notes structure, and add or remove
categories and subfolders as you see fit. The system honors taxonomy file order throughout —
the order you define in `taxonomy.local.yaml` is the order categories appear in classification
prompts, the ✱ Home note, and audit reports. No framework is enforced once you take ownership
of your taxonomy file.

---

## Further Reading

- [The PARA Method — Tiago Forte](https://fortelabs.com/blog/para/)
- [The PARA Method book](https://www.buildingasecondbrain.com/para)
- [Forever Notes framework](https://www.myforevernotes.com/docs/home)
- [config/taxonomy.zettelkasten.yaml](../config/taxonomy.zettelkasten.yaml) — Zettelkasten / Forever Notes taxonomy template
- [config/taxonomy.para.yaml](../config/taxonomy.para.yaml) — PARA taxonomy template
- [config/taxonomy.gtd.yaml](../config/taxonomy.gtd.yaml) — GTD taxonomy template
- [PLAN.md](../PLAN.md) — full implementation plan including classification pipeline and
  Forever Notes strict mode


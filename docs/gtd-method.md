# GTD Method — Taxonomy Guide for Apple Notes

> **Purpose of this document:**  
> This guide explains Getting Things Done (GTD), offers two ready-to-use taxonomy designs
> (standard and expanded), and provides decision guidance to help you choose and configure
> the right structure for your situation. It is also used as reference material when Claude
> generates a `taxonomy.local.yaml` for this project.
>
> GTD was created by David Allen. The canonical source is
> [gettingthingsdone.com](https://gettingthingsdone.com).

---

## What Is GTD?

Getting Things Done is a personal productivity system built around a single insight:
your brain is for **having** ideas, not **holding** them. By capturing every
commitment, task, and piece of information into a trusted external system — and
processing that capture regularly — you free cognitive resources for the work itself.

The system has five stages:

1. **Capture** — collect everything that has your attention into inboxes
2. **Clarify** — process each item: what is it, and is it actionable?
3. **Organize** — put it in the right place (action list, project list, reference, etc.)
4. **Reflect** — review regularly (especially a full weekly review)
5. **Engage** — do, with confidence that nothing is being forgotten

GTD's folder categories reflect the output of the Clarify step:

| Category | Definition | Actionable? |
|----------|-----------|-------------|
| **Inbox** | Raw captures not yet processed | Not yet determined |
| **Next Actions** | Concrete single physical actions to do ASAP | Yes |
| **Waiting For** | Delegated or externally blocked items to track | Yes (theirs, not yours) |
| **Projects** | Any outcome requiring more than one action step | Yes — via Next Action |
| **Someday/Maybe** | Intentions and ideas deferred to a future review | Not now |
| **Reference** | Non-actionable material kept for possible lookup | No |
| **Archive** | Completed or inactive items | No |

### A Note on Apple Notes vs. a Task Manager

GTD's action lists (Next Actions, Waiting For) work best in a dedicated task manager
(Things, OmniFocus, Todoist, Reminders) — not in a note-taking app. Apple Notes does not
have checkboxes that propagate to due-date views, reminder integration, or context
filtering. What Apple Notes does well is holding the **support material** for those
actions and projects: the reference documents, meeting notes, research, and project
context that you consult while executing.

In practice, a GTD taxonomy in Apple Notes means:

- **Next Actions** holds notes that support immediate work — not the action list itself
- **Waiting For** holds notes about what you're tracking and from whom — not a to-do list
- **Projects** holds project support material — not the project plan
- A task manager handles the actual action lists and reminders

This division keeps Apple Notes lean and lets each tool do what it does best.

---

## The Most Important GTD Distinctions

### Projects vs. Next Actions

In GTD, a **project** is any desired outcome that requires more than one action step
to complete. This is a broader definition than common usage:

- "Write the quarterly report" is a project (requires: research, draft, review, submit).
- "Email Sarah the quarterly report draft" is a next action (single, concrete, physical step).

The critical discipline: **every project must always have at least one identified Next
Action.** Without it, the project stalls. The weekly review is the moment you check that
every project on your list has its next action identified.

### Waiting For vs. Next Actions

Both are actionable, but the locus of action is different:

- **Next Action**: you are the person doing it, now or soon.
- **Waiting For**: someone else is doing it, and you are tracking that expectation.

If you send an email requesting approval, the "approve the document" item moves to Waiting
For. It reactivates as a Next Action only if it is late and you need to follow up.

### Someday/Maybe vs. Reference

Both are non-actionable at present, but for different reasons:

- **Reference**: static information. You keep it because you might need to look it up, not
  because you intend to act on it. It has no inherent review cycle.
- **Someday/Maybe**: an intention in suspension. You genuinely want to do this, just not
  now. It should be reviewed on a regular cadence (weekly review) to decide whether it
  becomes active or gets discarded.

The failure mode: putting real projects in Someday/Maybe and forgetting them, or filling
Reference with things that are actually Someday/Maybe intentions.

---

## Compatibility with the Forever Notes Framework

GTD and the Forever Notes framework operate at different levels and are complementary:

- **GTD** defines the organizational logic — whether a note is active, deferred, or
  reference material — and the processing discipline that keeps the system current.
- **Forever Notes** adds navigational infrastructure — the ✱ Home note, ✱ Hub notes,
  tags, and the heavy asterisk prefix for system notes.

You can use a GTD folder taxonomy and layer Forever Notes structural elements (strict mode)
on top. The `forever_notes_mode` setting in `settings.local.yaml` controls whether Hub
notes and tags are generated. In GTD + strict mode, Hub notes are particularly useful in
the Reference folder, where topic-based subfolders accumulate enough notes to benefit from
a cross-category index.

### Mapping GTD to the Broader Toolkit Taxonomy

The manage-apple-notes project's default taxonomy includes Zettelkasten-influenced
categories (Fleeting, Literature, Permanent) alongside more action-oriented categories.
If you use GTD, these map as follows:

| This project's default | GTD equivalent |
|------------------------|----------------|
| Inbox | Inbox — universal staging area before clarifying |
| Fleeting | Inbox (merge — fleeting notes are unprocessed captures) |
| Literature | Reference / Reading — notes tied to a specific source |
| Permanent | Reference / Ideas — refined evergreen material |
| Projects | Projects — project support material |
| Areas | Reference (no direct GTD equivalent; ongoing responsibilities are managed as recurring project reviews or Someday/Maybe lists) |
| Resources | Reference — general reference material |
| Archive | Archive |
| Review | Someday/Maybe (closest match) or a processing pass back to Inbox |

Switching to pure GTD replaces the nine-category Zettelkasten default with seven
categories, and the reference material that was split across Literature, Permanent, and
Resources collapses into a single Reference folder (with optional topic subfolders).

---

## Choosing Your Taxonomy

### Key Questions

Before choosing standard or expanded, consider:

1. **How many active projects do you typically have?**
   - 1–8 → standard (flat Projects folder is manageable)
   - 8–20 → expanded (per-project subfolders aid navigation and give the weekly
     review a clear checklist)
   - 20+ → expanded, and consider whether some "projects" are actually recurring
     habits or areas of responsibility

2. **How much Reference material do you accumulate?**
   - Moderate, mixed types → flat Reference folder with disciplined titling
   - Heavy, domain-specific → expanded Reference with topic subfolders

3. **Are you already using a task manager?**
   - Yes → the Next Actions and Waiting For folders in Apple Notes are thin
     (project support notes only); the expanded structure matters more for Projects
     and Reference
   - No → you may rely on Apple Notes more heavily for action lists; the standard
     design is still the better starting point, with per-project subfolders added later

4. **Are you migrating from an existing library or starting fresh?**
   - Migrating → start with the standard design; add per-project subfolders only
     for projects with more than 4–5 notes
   - Starting fresh → either works; the expanded design gives clear landing zones
     from day one

---

## Standard GTD Taxonomy

**Seven top-level folders.** One per GTD category, all flat. Navigation by search and
consistent note titling. This matches the canonical GTD reference implementation most
closely.

```
Inbox
Next Actions
Waiting For
Projects
Someday-Maybe
Reference
Archive
```

### Notes on the Standard Design

**Inbox** is the universal capture point. Nothing should stay here beyond your regular
processing pass. GTD recommends processing to empty at least weekly.

**Next Actions** holds notes in support of your current action list — context, background,
or materials you consult while executing. The action list itself lives in your task manager.
If you are not using a task manager, use disciplined note titles: `"[PROJECT] — [action]"`.

**Waiting For** holds one note per tracked delegation or dependency — who, what you
requested, and when. Review on every weekly review. Close notes when resolved.

**Projects** is flat. With up to 8–10 active projects, titling each note with the project
name is sufficient: `"Proposal — Budget Draft"`, `"Proposal — Stakeholder List"`.

**Someday/Maybe** holds genuine future intentions — not reference material, not abandoned
ideas. Every item here should have enough context to decide, during the weekly review,
whether it becomes active. Consider a brief note per item: what it is, why it might be
worth doing, and what the first step would be if activated.

**Reference** is flat. Everything non-actionable lives here: how-tos, factual reference,
research, notes from books, templates. Navigate by search. Well-chosen note titles matter
more here than anywhere else in the system.

**Archive** is flat. Completed projects and retired Someday/Maybe items move here without
renaming. The project or topic name in the note title is sufficient for future retrieval.

### When to Choose Standard

- You are migrating a large existing library and want quick results
- You have fewer than 8–10 active projects at any time
- Your Reference notes are varied but not so voluminous that browsing becomes friction
- You rely primarily on search for retrieval
- You are adopting GTD for the first time and want to start close to the canonical design

---

## Expanded GTD Taxonomy

**Seven top-level folders, ~15–25 folders total** (varying with active project and
reference domain count). Per-project subfolders in Projects and topic subfolders in
Reference.

```
Inbox

Next Actions

Waiting For

Projects
  └── [Project Name 1]
  └── [Project Name 2]
  └── [Project Name 3]
  └── ... (one subfolder per active project)

Someday-Maybe

Reference
  └── [Domain 1]
  └── [Domain 2]
  └── [Domain 3]
  └── ...

Archive
  └── Projects
  └── Reference
```

### Notes on the Expanded Design

**Projects** gets one subfolder per active project. Each subfolder collects all support
material for that project: meeting notes, research, drafts, stakeholder lists. When the
project completes, its subfolder moves to `Archive/Projects`. The weekly review becomes
a scan of the Projects top-level folder — each visible subfolder is an open commitment
that needs a current next action.

Project subfolders should be named simply and consistently: `"Home Renovation"`,
`"Q2 Product Launch"`, `"Spanish Course"`. Avoid dates in the subfolder name; dates
belong in note titles. The Archive move date is implicit in when the folder was archived.

**Reference** gets one subfolder per significant domain. Domain names should reflect
how you actually think about your reference material, not an idealized taxonomy.
Common patterns:

- **By subject**: `Health`, `Finance`, `Technology`, `Cooking`, `Career`
- **By type**: `How-Tos`, `Templates`, `Course Notes`, `Book Notes`
- **Hybrid**: subject subfolders for large domains, flat for smaller ones

A new Reference subfolder should only be created when a domain has accumulated enough
notes that browsing the flat Reference folder becomes friction — roughly 8 or more notes
on a distinct theme (matching the `min_notes_for_subfolder` threshold in
`settings.example.yaml`).

**Archive** has two mirroring subfolders so retired items land somewhere logical.
Archive is not searched often — its primary purpose is to keep active folders clean
while preserving material that might be useful later.

### When to Choose Expanded

- You have 8 or more active projects running simultaneously
- Your Reference collection is large enough that browsing a flat folder is friction
- You want the weekly review to work off a visible checklist (Projects subfolders)
- You intend to use Forever Notes strict mode — the Reference subfolders give Hub
  notes meaningful structure to index across

---

## Guidance for Claude: Generating `taxonomy.local.yaml`

When using Claude to generate or populate `taxonomy.local.yaml` based on this
document, provide the following as context alongside this file:

1. **Which taxonomy to use** — standard or expanded, or a custom variant.
2. **Your actual folder names** — Apple Notes folder names cannot contain
   certain special characters. Keep them short and clear.
3. **Your active projects** — for the expanded set, list current project names
   so Claude can pre-populate the Projects subfolders list.
4. **Your Reference domains** — confirm or define the domain subfolders that
   reflect how your reference material is actually organized.
5. **Your operating mode** — `loose` (folders only) or `strict` (folders plus
   Forever Notes Hub notes and tags).

### Sample Prompt for Claude

```
Using the GTD taxonomy guidance in docs/gtd-method.md, generate a
taxonomy.local.yaml for my Apple Notes library. I want the [standard /
expanded] set. My active projects are: [list]. My main reference domains
are: [list]. I am using [loose / strict] mode. My iCloud Notes account is
the primary account.
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
- Reference subfolders — should reflect how your material is actually organized,
  not an aspirational structure

### Additional Settings Step

GTD uses category keys (`next_actions`, `waiting_for`, `someday_maybe`, `reference`)
that are not in the built-in taxonomy defaults. When GTD is chosen, `notes setup`
prints a YAML snippet to add to the `categories:` block of `settings.local.yaml`
so the classifier and audit use the correct descriptions and stale-day thresholds.
Add this snippet before running `notes classify` for the first time.

---

## Quick Reference: GTD in One Table

| Folder | Contains | Lifecycle | Subfolders |
|--------|----------|-----------|------------|
| Inbox | Unprocessed captures | Transient — process regularly | None |
| Next Actions | Project support material for current actions | Active — retire when action completes | None |
| Waiting For | Tracked delegations and dependencies | Active — close when resolved | None |
| Projects | Support material for active multi-step outcomes | Transient — retire to Archive on completion | One per project (expanded) or none (standard) |
| Someday/Maybe | Genuine future intentions for regular review | Deferred — activate or discard at weekly review | None |
| Reference | Non-actionable material kept for lookup | Permanent — accumulates over time | By domain (expanded) or none (standard) |
| Archive | Completed or inactive items from all categories | Permanent — rarely accessed | Mirroring subfolders (expanded) or none (standard) |

---

## The Weekly Review

GTD's weekly review is what keeps the system trustworthy. Without it, the system
gradually ceases to reflect reality and the psychological benefits disappear. In
Apple Notes, the weekly review touches every GTD folder:

1. **Process Inbox to empty** — clarify every capture; file or delete.
2. **Review Next Actions** — are these still relevant? Are there stale notes for
   completed actions?
3. **Review Waiting For** — is anything overdue? Is a follow-up needed?
4. **Review Projects** — does every project have a current Next Action identified?
   Any recently completed projects to archive?
5. **Review Someday/Maybe** — does anything become active now? Does anything get
   discarded?
6. **Review Reference** — optional; scan for notes that no longer belong.

The weekly review is also the moment to prune Apple Notes: delete duplicates, archive
completed project notes, and retire stale Waiting For items.

---

## Customization

Both GTD designs above are starting points. Copy `config/taxonomy.gtd.yaml` to
`taxonomy.local.yaml`, rename folders to match your Apple Notes structure, and add or
remove categories and subfolders as you see fit. The system honors taxonomy file order
throughout — the order you define in `taxonomy.local.yaml` is the order categories
appear in classification prompts, the ✱ Home note, and audit reports. No framework is
enforced once you take ownership of your taxonomy file.

One common adaptation: merge **Waiting For** into **Next Actions** if you don't have
many delegations to track. Another: rename **Someday/Maybe** to something that fits
your thinking style — `Later`, `Incubating`, or `On Hold` all work equally well.

---

## Further Reading

- [Getting Things Done — David Allen (gettingthingsdone.com)](https://gettingthingsdone.com)
- [Getting Things Done — Book (Penguin Random House)](https://www.penguinrandomhouse.com/books/303727/getting-things-done-by-david-allen/)
- [Forever Notes framework](https://www.myforevernotes.com/docs/home)
- [config/taxonomy.gtd.yaml](../config/taxonomy.gtd.yaml) — GTD taxonomy template
- [config/taxonomy.para.yaml](../config/taxonomy.para.yaml) — PARA taxonomy template
- [config/taxonomy.zettelkasten.yaml](../config/taxonomy.zettelkasten.yaml) — Zettelkasten / Forever Notes taxonomy template
- [docs/para-method.md](para-method.md) — PARA method guide
- [docs/forever-notes-framework.md](forever-notes-framework.md) — Forever Notes framework reference

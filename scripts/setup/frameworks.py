"""Framework reference data for the notes setup wizard."""

from __future__ import annotations

FRAMEWORKS: dict[str, dict] = {
    "PARA": {
        "name": "PARA",
        "full_name": "Projects · Areas · Resources · Archive",
        "creator": "Tiago Forte",
        "organizing_principle": "Actionability — file by how active something is, not by topic",
        "category_keys": ["inbox", "projects", "areas", "resources", "archive"],
        "canonical_names": {
            "inbox": "Inbox",
            "projects": "Projects",
            "areas": "Areas",
            "resources": "Resources",
            "archive": "Archive",
        },
        "category_prompts": {
            "inbox": "Inbox  (unprocessed captures, cleared weekly)",
            "projects": "Projects  (active work with a deadline or defined outcome)",
            "areas": "Areas  (ongoing responsibilities that never really end)",
            "resources": "Resources  (reference material and topics you follow)",
            "archive": "Archive  (completed, inactive, or outdated notes)",
        },
        "folder_preview": "Inbox  /  Projects  /  Areas  /  Resources  /  Archive",
        "best_for": "Digital generalists who want low-friction organization across work and life",
        "maintenance": "Low",
        "weakness": "No built-in idea-linking; search and tags fill that gap at scale",
        "rationale_template": (
            "PARA organizes by actionability rather than topic, which matches a library "
            "spread across {folder_count} folders. Its four buckets are easy to apply "
            "consistently, and {maintenance_note}."
        ),
    },
    "GTD": {
        "name": "GTD",
        "full_name": "Getting Things Done",
        "creator": "David Allen",
        "organizing_principle": "Capture everything; clarify actionability; weekly review",
        "category_keys": [
            "inbox",
            "next_actions",
            "waiting_for",
            "projects",
            "someday_maybe",
            "reference",
            "archive",
        ],
        "canonical_names": {
            "inbox": "Inbox",
            "next_actions": "Next Actions",
            "waiting_for": "Waiting For",
            "projects": "Projects",
            "someday_maybe": "Someday-Maybe",
            "reference": "Reference",
            "archive": "Archive",
        },
        "category_prompts": {
            "inbox": "Inbox  (raw captures, processed to empty at least weekly)",
            "next_actions": "Next Actions  (concrete single tasks to do ASAP)",
            "waiting_for": "Waiting For  (items delegated or blocked on someone else)",
            "projects": "Projects  (multi-step outcomes to complete)",
            "someday_maybe": "Someday-Maybe  (deferred ideas to revisit someday)",
            "reference": "Reference  (non-actionable material to keep)",
            "archive": "Archive  (completed or inactive items)",
        },
        "folder_preview": (
            "Inbox  /  Next Actions  /  Waiting For  /  Projects  /  Someday-Maybe  "
            "/  Reference  /  Archive"
        ),
        "best_for": "People overwhelmed by tasks and commitments who need a trusted system",
        "maintenance": "Medium — weekly review is non-negotiable",
        "weakness": "A task system first; notes play a supporting reference role",
        "rationale_template": (
            "GTD is ideal when task clarity is the primary need. "
            "Your notes show {task_signal} action-oriented content, "
            "and the weekly review habit keeps commitments from slipping."
        ),
        # Non-standard category keys need explicit metadata in settings.local.yaml
        "extra_categories": {
            "next_actions": {
                "description": "concrete next actions — single tasks to do ASAP",
                "active_days": 14,
            },
            "waiting_for": {
                "description": "items delegated or blocked on someone else",
                "stale_days": 14,
            },
            "someday_maybe": {
                "description": "deferred ideas and projects",
            },
            "reference": {
                "description": "reference material — not actionable",
                "exclude_from_classify": True,
            },
        },
    },
    "ZETTELKASTEN": {
        "name": "Zettelkasten",
        "full_name": "Zettelkasten (Slip-Box Method)",
        "creator": "Niklas Luhmann",
        "organizing_principle": "Linked atomic ideas — one concept per note, every note connected",
        "category_keys": [
            "inbox",
            "fleeting",
            "literature",
            "permanent",
            "projects",
            "areas",
            "resources",
            "archive",
            "review",
        ],
        "canonical_names": {
            "inbox": "Inbox",
            "fleeting": "Fleeting",
            "literature": "Literature",
            "permanent": "Permanent",
            "projects": "Projects",
            "areas": "Areas",
            "resources": "Resources",
            "archive": "Archive",
            "review": "Review",
        },
        "category_prompts": {
            "inbox": "Inbox  (quick captures, processed within 48 hours)",
            "fleeting": "Fleeting  (short-lived thoughts, not yet processed into permanent notes)",
            "literature": "Literature  (notes tied to a specific book, article, or talk)",
            "permanent": "Permanent  (refined, evergreen ideas in your own words)",
            "projects": "Projects  (notes tied to active projects)",
            "areas": "Areas  (ongoing responsibilities)",
            "resources": "Resources  (reference material and collections)",
            "archive": "Archive  (inactive or completed notes)",
            "review": "Review  (notes awaiting classification — catch-all)",
        },
        "folder_preview": (
            "Inbox  /  Fleeting  /  Literature  /  Permanent  /  "
            "Projects  /  Areas  /  Resources  /  Archive  /  Review"
        ),
        "best_for": "Writers, researchers, and thinkers building long-term compounding knowledge",
        "maintenance": "High — every note must be processed and linked deliberately",
        "weakness": "Apple Notes lacks native backlinks; requires consistent discipline",
        "rationale_template": (
            "Zettelkasten rewards libraries where ideas build on each other over time. "
            "{cross_ref_note}"
            "The extra folder structure pays off when ideas compound across months and years."
        ),
    },
    "EXISTING": {
        "name": "Existing Organization",
        "improvement_suggestions": [
            "Create a single Inbox folder — capture everything there first, then file it.",
            "Adopt a consistent date-prefix naming convention: YYYY-MM-DD Topic.",
            "Once a month, move notes untouched for 6+ months to an Archive folder.",
        ],
        # Category roles used to map existing folders; presented as plain-English prompts.
        # Defaults are intentionally empty so pressing Enter skips the role.
        "mapping_prompts": {
            "inbox": "Inbox / capture folder  (unprocessed notes, cleared regularly — blank to skip)",
            "projects": "Projects / active work folder  (notes with a deadline or defined outcome — blank to skip)",
            "areas": "Areas / responsibilities folder  (ongoing work that never really ends — blank to skip)",
            "resources": "Resources / reference folder  (material you keep but don't act on — blank to skip)",
            "archive": "Archive folder  (completed or inactive notes — blank to skip)",
        },
    },
}


def get_framework(key: str) -> dict:
    """Return framework data by key (case-insensitive). Raises KeyError if not found."""
    return FRAMEWORKS[key.upper()]


def framework_choices() -> list[str]:
    """Return display labels for the three main framework choices."""
    return [
        "PARA — Projects, Areas, Resources, Archive  (recommended for most people)",
        "GTD — Getting Things Done  (great if tasks and commitments are your main pain)",
        "Zettelkasten — Linked atomic notes  (best for writers/researchers building knowledge over time)",
        "Use what I already have — map my existing folders, get improvement suggestions",
    ]

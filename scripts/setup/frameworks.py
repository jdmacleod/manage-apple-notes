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
            "inbox": "capture / inbox  (unprocessed notes, processed weekly)",
            "projects": "projects  (active work with a deadline or defined outcome)",
            "areas": "areas  (ongoing responsibilities that never really end)",
            "resources": "resources  (reference material, topics you follow)",
            "archive": "archive  (completed, inactive, or outdated notes)",
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
            "inbox": "inbox  (raw captures, processed to empty at least weekly)",
            "next_actions": "next actions  (concrete single tasks to do ASAP)",
            "waiting_for": "waiting for  (items delegated or blocked on someone else)",
            "projects": "projects  (multi-step outcomes to complete)",
            "someday_maybe": "someday/maybe  (deferred ideas to revisit someday)",
            "reference": "reference  (non-actionable material to keep)",
            "archive": "archive  (completed or inactive items)",
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
            "inbox": "inbox  (quick captures, processed within 48 hours)",
            "fleeting": "fleeting  (short-lived thoughts not yet processed into permanent notes)",
            "literature": "literature  (notes tied to a specific book, article, or talk)",
            "permanent": "permanent  (refined, evergreen ideas in your own words)",
            "projects": "projects  (notes tied to active projects)",
            "areas": "areas  (ongoing responsibilities)",
            "resources": "resources  (reference material and collections)",
            "archive": "archive  (inactive or completed notes)",
            "review": "review  (notes awaiting classification — catch-all)",
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
        # Category roles used to map existing folders; presented as plain-English prompts
        "mapping_prompts": {
            "inbox": "Which folder is your capture inbox?  (unprocessed notes, cleared regularly)",
            "projects": "Which folder holds active project notes?  (or leave blank to skip)",
            "areas": "Which folder holds ongoing area / responsibility notes?  (or blank to skip)",
            "resources": "Which folder holds reference / resource notes?  (or blank to skip)",
            "archive": "Which folder is your archive?  (completed or old notes, or blank to skip)",
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

"""
All LLM prompts for the journal graph RAG system.
"""

EXTRACT_PROMPT = """\
You are an entity extraction engine for a personal journal system.

Given a journal entry, extract every distinct entity mention. For each, output:
- mention: the entity name as the user refers to it
- entity_type: one of event, person, goal, habit, place, class, project
- domain: one of career, wealth, love, social, study, general
- snippet: a 1-2 sentence excerpt from the journal that captures what the user said about this entity
- events: list of upcoming events tied to this entity. Each has label, date (ISO format YYYY-MM-DD), detail. Empty list if none.
- state_change: null, or one of "completed", "abandoned" if the journal indicates the entity is finished/dropped
- relations: list of other entity mentions from THIS entry that this entity is related to. Each has mention (the other entity's mention string) and relation (a short label like "friend_of", "part_of", "works_at", "studies_with", "blocks", "helps").

Rules:
- Extract ALL entities: people, projects, goals, classes, habits, places, events
- Dates: interpret relative dates (e.g. "next Monday", "in 3 days") relative to the entry date provided
- State changes: "got rejected from X" → X is abandoned. "finished X" / "X went well" for one-time events → completed. Only mark state_change for clear finality.
- Snippets should be taken verbatim or near-verbatim from the journal text
- If the same entity appears multiple times, merge into one extraction with the richest snippet
- Do NOT extract the user themselves as an entity

Today's date: {entry_date}

Journal entry:
{diary_entry}

Output as JSON array of extractions.
"""

CONTEXT_DOC_PROMPT = """\
You are building a rich context document for a domain item in a personal knowledge graph.

Given the following data about "{title}" ({item_type} in {domain}):

Current summary: {summary}

Recent interactions (journal snippets):
{interactions}

Upcoming events:
{events}

Connected entities:
{connections}

Write a single rich paragraph (200-400 words) that captures everything known about this entity.
Include: what it is, current status, recent developments, upcoming deadlines, key relationships.
Write in third person, factual tone. This text will be embedded for semantic search.
"""

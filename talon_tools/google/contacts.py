"""
Google Contacts (People API) — search and list contacts.

Sync functions — wrap in run_in_executor() for async.
"""

from __future__ import annotations

from googleapiclient.discovery import build

from .auth import get_credentials


def _service(token_file=None):
    return build("people", "v1", credentials=get_credentials(token_file))


PERSON_FIELDS = "names,emailAddresses,phoneNumbers,organizations,birthdays"


def _format_person(p: dict) -> str:
    """Format a person resource into a readable string."""
    names = p.get("names", [])
    name = names[0].get("displayName", "(no name)") if names else "(no name)"

    parts = [name]

    for email in p.get("emailAddresses", []):
        parts.append(f"  email: {email['value']}")

    for phone in p.get("phoneNumbers", []):
        parts.append(f"  phone: {phone['value']}")

    for org in p.get("organizations", []):
        title = org.get("title", "")
        company = org.get("name", "")
        if company or title:
            parts.append(f"  org: {', '.join(x for x in [title, company] if x)}")

    for bday in p.get("birthdays", []):
        date = bday.get("date", {})
        if date:
            parts.append(f"  birthday: {date.get('year', '??')}-{date.get('month', '??'):02}-{date.get('day', '??'):02}")

    return "\n".join(parts)


def search_contacts(query: str, max_results: int = 10, token_file=None) -> str:
    """Search contacts by name, email, or phone."""
    svc = _service(token_file)
    result = svc.people().searchContacts(
        query=query,
        pageSize=min(max_results, 30),
        readMask=PERSON_FIELDS,
    ).execute()

    people = [r["person"] for r in result.get("results", [])]
    if not people:
        return f"No contacts found for: {query}"

    return "\n---\n".join(_format_person(p) for p in people)


def list_contacts(max_results: int = 20, token_file=None) -> str:
    """List contacts ordered by last updated."""
    svc = _service(token_file)
    result = svc.people().connections().list(
        resourceName="people/me",
        pageSize=min(max_results, 100),
        personFields=PERSON_FIELDS,
        sortOrder="LAST_MODIFIED_DESCENDING",
    ).execute()

    people = result.get("connections", [])
    if not people:
        return "No contacts found."

    return "\n---\n".join(_format_person(p) for p in people)

"""Transparent OSM hospital triage rules for emergency routing."""

from __future__ import annotations

import re
import unicodedata

EXCLUSION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "specialty clinic or care service": (
        "clinic", "eye", "ophthalm", "dental", "dentist", "skin", "dermat",
        "spectacle", "lens", "pharmacy", "diagnostic", "laboratory", "lab ",
        "veterinary", "ayurved", "physiotherap", "physio", "optical", "optician",
    ),
}
EMERGENCY_NAME_KEYWORDS = ("hospital", "medical college", "trauma")
JUNK_NAME_KEYWORDS = ("hehehe", "hahaha", "asdf", "test hospital", "unknown")


def normalize_hospital_name(name: str) -> str:
    """Normalize a place name for nearby duplicate detection."""
    decomposed = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().casefold()
    return " ".join(re.findall(r"[a-z0-9]+", decomposed))


def classify_hospital(entry: dict[str, object]) -> tuple[str | None, str]:
    """Return (tier, reason); exclusions override all emergency indicators.

    Tier rule: emergency=yes, a nonempty beds tag, or a name containing
    hospital/medical college/trauma qualifies as emergency-capable. Specialty
    service keywords in the name or healthcare tags exclude the entry first.
    Unnamed entries are kept only with emergency=yes. Other entries are
    excluded as lacking evidence suitable for emergency routing.
    """
    name = str(entry.get("name", ""))
    if name:
        letters = [character for character in name if character.isalpha()]
        words = re.findall(r"[A-Za-z]+", name)
        normalized = normalize_hospital_name(name)
        if len(letters) < 4:
            return None, "junk name: fewer than four alphabetic letters"
        if not any(character.casefold() in "aeiou" for character in letters):
            return None, "junk name: no vowel"
        if not words:
            return None, "junk name: no alphabetic word"
        if any(keyword in normalized for keyword in JUNK_NAME_KEYWORDS):
            return None, "junk name: placeholder or test text"
    searchable = " ".join(
        str(entry.get(key, ""))
        for key in ("name", "healthcare", "healthcare:speciality", "amenity")
    ).casefold()
    for reason, keywords in EXCLUSION_KEYWORDS.items():
        matched = next((word for word in keywords if word in searchable), None)
        if matched:
            return None, f"{reason}: matched '{matched}'"

    emergency = str(entry.get("emergency", "")).casefold() == "yes"
    beds = str(entry.get("beds", "")).strip()
    name_evidence = any(word in name.casefold() for word in EMERGENCY_NAME_KEYWORDS)
    if emergency:
        return "emergency", "emergency=yes"
    if beds:
        return "emergency", "beds tag present"
    if name_evidence:
        return "emergency", "emergency-capable name keyword"
    if not name:
        return None, "unnamed and emergency=yes is absent"
    return None, "no emergency-capability evidence"


def filter_hospital_entries(
    entries: list[dict[str, object]], duplicate_radius_m: float = 150.0
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Classify entries and exclude nearby same-name duplicates with reasons."""
    from safepassage.algorithms.geo import haversine

    kept: list[dict[str, object]] = []
    excluded: list[dict[str, object]] = []
    by_name: dict[str, list[dict[str, object]]] = {}
    for raw_entry in entries:
        entry = dict(raw_entry)
        tier, reason = classify_hospital(entry)
        if tier is None:
            entry["exclusion_reason"] = reason
            excluded.append(entry)
            continue
        normalized = normalize_hospital_name(str(entry.get("name", "")))
        duplicate = None
        if normalized:
            for existing in by_name.get(normalized, []):
                separation = haversine(
                    float(existing["lat"]), float(existing["lng"]),
                    float(entry["lat"]), float(entry["lng"]),
                )
                if separation <= duplicate_radius_m:
                    duplicate = existing
                    break
        if duplicate is not None:
            entry["exclusion_reason"] = (
                f"nearby duplicate of OSM {duplicate.get('osm_type')} {duplicate.get('osm_id')} "
                f"within {duplicate_radius_m:.0f} m"
            )
            excluded.append(entry)
            continue
        entry["tier"] = tier
        entry["classification_reason"] = reason
        kept.append(entry)
        if normalized:
            by_name.setdefault(normalized, []).append(entry)
    return kept, excluded

"""Feature registry — indexes entries for fast querying.

The registry loads all entries once and provides query methods
for the detection engine, fix engine, and other consumers.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .loader import load_all_entries, load_all_language_metas, load_language_meta
from .schema import Direction, FeatureEntry, LanguageMeta
from .version import parse_version, version_above

logger = logging.getLogger(__name__)


class FeatureRegistry:
    """In-memory index of all feature database entries.

    Loaded once at startup. Provides query methods for:
    - Lookup by ID
    - Filter by language
    - Filter by version (above/below target)
    - Filter by category
    - Filter by direction
    - Search by name/tags
    """

    def __init__(self) -> None:
        self._entries: dict[str, FeatureEntry] = {}
        self._by_language: dict[str, list[FeatureEntry]] = {}
        self._by_category: dict[str, dict[str, list[FeatureEntry]]] = {}
        self._metas: dict[str, LanguageMeta] = {}

    _singleton: FeatureRegistry | None = None
    _singleton_dir: Path | None = None

    @classmethod
    def load(
        cls,
        entries_dir: Path | None = None,
        language: str | None = None,
    ) -> FeatureRegistry:
        """Load entries and build the registry.

        Uses a singleton cache — the registry is only built once per process.
        Call invalidate() to force a reload.

        Args:
            entries_dir: Override entries directory (default: database/entries/)
            language: Only load entries for this language (e.g., "python").
                      Default: all languages.
        """
        if cls._singleton is not None and cls._singleton_dir == entries_dir:
            return cls._singleton

        registry = cls()
        entries = load_all_entries(entries_dir, language=language)
        for entry in entries:
            registry._add(entry)
        registry._metas = load_all_language_metas(entries_dir)

        cls._singleton = registry
        cls._singleton_dir = entries_dir

        logger.info(
            "Feature registry: %d entries, %d languages",
            len(registry._entries),
            len(registry._by_language),
        )
        return registry

    @classmethod
    def invalidate(cls) -> None:
        """Clear the singleton cache — forces reload on next load()."""
        cls._singleton = None
        cls._singleton_dir = None

    def _add(self, entry: FeatureEntry) -> None:
        """Add an entry to the index."""
        if entry.id in self._entries:
            logger.warning("Duplicate entry ID: %s (skipping)", entry.id)
            return

        self._entries[entry.id] = entry

        # Index by language
        self._by_language.setdefault(entry.language, []).append(entry)

        # Index by language + category
        lang_cats = self._by_category.setdefault(entry.language, {})
        lang_cats.setdefault(entry.category, []).append(entry)

    # ── Query methods ────────────────────────────────────────────

    def get(self, feature_id: str) -> FeatureEntry | None:
        """Get an entry by its unique ID."""
        return self._entries.get(feature_id)

    def by_language(self, language: str) -> list[FeatureEntry]:
        """Get all entries for a language."""
        return list(self._by_language.get(language, []))

    def above_version(self, language: str, target: str) -> list[FeatureEntry]:
        """Get entries introduced ABOVE the target version.

        Used for downgrade: "what features does this code use
        that aren't available in the target version?"
        """
        entries = self._by_language.get(language, [])
        return [
            e for e in entries
            if version_above(language, e.introduced, target)
            and e.direction in (Direction.DOWNGRADE, Direction.BOTH)
        ]

    def below_version(self, language: str, target: str) -> list[FeatureEntry]:
        """Get entries introduced BELOW the target version.

        Used for upgrade: "what backports/workarounds can be removed
        now that we're targeting a newer version?"
        """
        entries = self._by_language.get(language, [])
        return [
            e for e in entries
            if not version_above(language, e.introduced, target)
            and e.direction in (Direction.UPGRADE, Direction.BOTH)
        ]

    def by_category(self, language: str, category: str) -> list[FeatureEntry]:
        """Get entries in a specific category."""
        return list(self._by_category.get(language, {}).get(category, []))

    def by_direction(self, language: str, direction: str) -> list[FeatureEntry]:
        """Get entries for a specific direction."""
        try:
            dir_enum = Direction(direction)
        except ValueError:
            return []
        entries = self._by_language.get(language, [])
        return [
            e for e in entries
            if e.direction == dir_enum or e.direction == Direction.BOTH
        ]

    def search(self, query: str) -> list[FeatureEntry]:
        """Search entries by name, description, or tags."""
        query_lower = query.lower()
        results = []
        for entry in self._entries.values():
            if (
                query_lower in entry.feature_name.lower()
                or query_lower in entry.description.lower()
                or query_lower in entry.id.lower()
                or any(query_lower in tag.lower() for tag in entry.tags)
            ):
                results.append(entry)
        return results

    def languages(self) -> list[str]:
        """List all languages with entries."""
        return sorted(self._by_language.keys())

    def language_meta(self, language: str) -> LanguageMeta | None:
        """Get metadata for a language."""
        return self._metas.get(language)

    # ── Statistics ───────────────────────────────────────────────

    def count(self) -> int:
        """Total number of entries."""
        return len(self._entries)

    def count_by_language(self) -> dict[str, int]:
        """Entry count per language."""
        return {lang: len(entries) for lang, entries in self._by_language.items()}

    def count_by_category(self, language: str) -> dict[str, int]:
        """Entry count per category for a language."""
        return {
            cat: len(entries)
            for cat, entries in self._by_category.get(language, {}).items()
        }

    def stats(self) -> dict:
        """Full statistics."""
        return {
            "total": self.count(),
            "by_language": self.count_by_language(),
            "languages": self.languages(),
        }

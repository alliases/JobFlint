from typing import List, Optional

from app.schemas.job import ParsedVacancy


class FilterEngine:
    def __init__(
        self,
        keywords: Optional[List[str]] = None,
        location: Optional[str] = None,
        salary_min: Optional[int] = None,
    ):
        """Initialize the filter engine with optional keyword, location, and salary rules."""
        self.keywords = [k.lower() for k in keywords] if keywords else None
        self.location = location.lower() if location else None
        self.salary_min = salary_min

    def passes(self, vacancy: ParsedVacancy) -> bool:
        """Return True if the vacancy satisfies all active filter rules."""
        if not self._matches_keywords(vacancy):
            return False
        if not self._matches_location(vacancy):
            return False
        if not self._meets_salary(vacancy):
            return False
        return True

    def _matches_keywords(self, vacancy: ParsedVacancy) -> bool:
        """Check if vacancy matches any of the required keywords."""
        if not self.keywords:
            return True

        search_text = (vacancy.title + " " + " ".join(vacancy.skills)).lower()
        return any(keyword in search_text for keyword in self.keywords)

    def _matches_location(self, vacancy: ParsedVacancy) -> bool:
        """Check if vacancy matches the required location."""
        if not self.location:
            return True
        if not vacancy.location:
            return False
        return self.location in vacancy.location.lower()

    def _meets_salary(self, vacancy: ParsedVacancy) -> bool:
        """Check if vacancy meets the minimum salary requirement."""
        if not self.salary_min:
            return True
        if not vacancy.salary_min:
            return False
        return vacancy.salary_min >= self.salary_min

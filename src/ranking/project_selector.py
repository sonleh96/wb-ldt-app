"""Deterministic project selection from scored ranking outputs."""

from src.ranking.project_scorer import ScoredProject


class ProjectSelector:
    """Select top projects from deterministic scoring outputs."""

    def select_projects(self, *, scored_projects: list[ScoredProject], top_n: int) -> tuple[list[ScoredProject], list[ScoredProject]]:
        """Return selected projects and excluded projects."""

        eligible = [item for item in scored_projects if not item.exclusion_reasons]
        excluded = [item for item in scored_projects if item.exclusion_reasons]

        ordered = sorted(
            eligible,
            key=lambda item: (-item.total_score, item.project_id, item.title),
        )
        ordered_excluded = sorted(
            excluded,
            key=lambda item: (item.project_id, item.title),
        )
        return ordered[:top_n], ordered_excluded

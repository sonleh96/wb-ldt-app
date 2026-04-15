"""Service-layer orchestration and business logic."""

from src.schemas.workflow import RetrievalPlan


CATEGORY_VOCABULARY: dict[str, dict[str, list[str]]] = {
    "Environment": {
        "must_have": ["air quality", "waste", "municipal service", "public investment"],
        "should_have": ["emissions", "recycling", "transfer station", "monitoring"],
        "exclude": ["marketing", "tourism"],
    },
    "Sustainable Transport": {
        "must_have": ["transport", "road", "rail", "public investment"],
        "should_have": ["mobility", "resilience", "flood risk", "heat risk"],
        "exclude": ["private aviation"],
    },
}


class QueryPlanner:
    """Service for QueryPlanner workflows and operations."""

    def build_retrieval_plan(
        self,
        *,
        municipality_id: str,
        category: str,
        year: int,
        priority_signals: list[dict[str, object]],
        top_k: int = 10,
    ) -> RetrievalPlan:
        """Build retrieval plan."""
        vocab = CATEGORY_VOCABULARY.get(
            category,
            {
                "must_have": ["municipal development", "public investment"],
                "should_have": ["policy", "project readiness"],
                "exclude": [],
            },
        )

        indicator_terms = [
            str(item.get("indicator_name", "")).strip()
            for item in priority_signals[:3]
            if str(item.get("indicator_name", "")).strip()
        ]

        must_have = list(dict.fromkeys([*vocab["must_have"], *indicator_terms]))
        should_have = list(dict.fromkeys(vocab["should_have"]))
        exclude = list(dict.fromkeys(vocab["exclude"]))

        intent_query = (
            f"Municipality {municipality_id} {category} public investment priorities and implementation evidence"
        )
        evidence_query = (
            f"{category} evidence for indicator gaps: {', '.join(indicator_terms) if indicator_terms else 'core indicators'}"
        )
        constraint_query = (
            f"Geography={municipality_id}; Category={category}; Year<={year}; Source trust=policy,dataset,project_document"
        )

        query = " ".join([intent_query, evidence_query, constraint_query]).strip()

        return RetrievalPlan(
            municipality_id=municipality_id,
            category=category,
            query=query,
            intent_query=intent_query,
            evidence_query=evidence_query,
            constraint_query=constraint_query,
            query_terms={
                "must_have": must_have,
                "should_have": should_have,
                "exclude": exclude,
            },
            retrieval_mode="hybrid",
            filters={"category": category, "municipality_id": municipality_id},
            top_k=top_k,
        )

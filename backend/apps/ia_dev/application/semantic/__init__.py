_EXPORTS = {
    "CauseDiagnosticsService": ".cause_diagnostics_service",
    "CanonicalResolutionService": ".canonical_resolution_service",
    "ContextBuilder": ".context_builder",
    "ColumnSemanticResolver": ".column_semantic_resolver",
    "QueryExecutionPlanner": ".query_execution_planner",
    "QueryIntentResolver": ".query_intent_resolver",
    "QueryPatternMemoryService": ".query_pattern_memory_service",
    "SemanticNormalizationService": ".semantic_normalization_service",
    "RelationSemanticResolver": ".relation_semantic_resolver",
    "ResultSatisfactionValidator": ".result_satisfaction_validator",
    "SatisfactionReviewGate": ".satisfaction_review_gate",
    "RuleSemanticResolver": ".rule_semantic_resolver",
    "SemanticBusinessResolver": ".semantic_business_resolver",
    "SynonymSemanticResolver": ".synonym_semantic_resolver",
}

__all__ = list(_EXPORTS.keys())


def __getattr__(name):
    module_name = _EXPORTS.get(name)
    if not module_name:
        raise AttributeError(name)
    module = __import__(f"{__name__}{module_name}", fromlist=[name])
    return getattr(module, name)

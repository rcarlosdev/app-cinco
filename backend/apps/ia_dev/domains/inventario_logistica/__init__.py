from .inventory_dictionary_audit import InventoryDictionaryAuditService
from .inventory_dictionary_sync import InventoryDictionarySyncService
from .inventory_query_examples import get_inventory_query_examples
from .response_assembler import build_inventory_business_response
from .yaml_agent_loader import (
    get_business_concepts,
    get_business_rules,
    get_examples_as_query_patterns,
    get_fields_for_dictionary,
    get_groupable_dimensions,
    get_relationships_for_dictionary,
    get_synonyms_for_dictionary,
    get_tables_for_dictionary,
    load_inventory_agent_yaml,
    validate_yaml_integrity,
)

__all__ = [
    "InventoryDictionaryAuditService",
    "InventoryDictionarySyncService",
    "InventorySemanticResolver",
    "build_inventory_business_response",
    "get_inventory_query_examples",
    "load_inventory_agent_yaml",
    "get_tables_for_dictionary",
    "get_fields_for_dictionary",
    "get_relationships_for_dictionary",
    "get_synonyms_for_dictionary",
    "get_groupable_dimensions",
    "get_business_concepts",
    "get_business_rules",
    "get_examples_as_query_patterns",
    "validate_yaml_integrity",
]


def __getattr__(name):
    if name == "InventorySemanticResolver":
        from .semantic_inventory_resolver import InventorySemanticResolver

        return InventorySemanticResolver
    raise AttributeError(name)

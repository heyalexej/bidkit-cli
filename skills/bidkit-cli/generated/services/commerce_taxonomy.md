# Taxonomy API

- **Service key:** `commerce_taxonomy`
- **CLI:** `bidkit commerce taxonomy`
- **Version:** v1.1.1
- **Base path:** `/commerce/taxonomy/v1`  ·  **Subdomain:** `api`
- **Auth scheme:** `Bearer`  ·  **Requires signature:** False
- **Source spec:** `commerce_taxonomy_v1_oas3.json`
- **Operations:** 9

Inspect any operation's full metadata or schema without a network call:

```bash
bidkit api describe commerce_taxonomy.OPERATION_ID
bidkit api schema commerce_taxonomy.OPERATION_ID request
```

| Operation key | Method | Path | Risk | Summary |
|---|---|---|---|---|
| `commerce_taxonomy.fetchItemAspects` | GET | `/category_tree/{category_tree_id}/fetch_item_aspects` | read | Get Aspects for All Leaf Categories in a Marketplace |
| `commerce_taxonomy.getCategorySubtree` | GET | `/category_tree/{category_tree_id}/get_category_subtree` | read | Get a Category Subtree |
| `commerce_taxonomy.getCategorySuggestions` | GET | `/category_tree/{category_tree_id}/get_category_suggestions` | read | Get Suggested Categories |
| `commerce_taxonomy.getCategoryTree` | GET | `/category_tree/{category_tree_id}` | read | Get a Category Tree |
| `commerce_taxonomy.getCompatibilityProperties` | GET | `/category_tree/{category_tree_id}/get_compatibility_properties` | read | Get Compatibility Properties |
| `commerce_taxonomy.getCompatibilityPropertyValues` | GET | `/category_tree/{category_tree_id}/get_compatibility_property_values` | read | Get Compatibility Property Values |
| `commerce_taxonomy.getDefaultCategoryTreeId` | GET | `/get_default_category_tree_id` | read | Get a Default Category Tree ID |
| `commerce_taxonomy.getExpiredCategories` | GET | `/category_tree/{category_tree_id}/get_expired_categories` | read | This method retrieves the mappings of expired leaf categories in the specified category tr |
| `commerce_taxonomy.getItemAspectsForCategory` | GET | `/category_tree/{category_tree_id}/get_item_aspects_for_category` | read | This call returns a list of aspects that are appropriate or necessary for accurately descr |

Command path prefix: `bidkit commerce taxonomy <operation>`.

## Examples

```bash
# commerce_taxonomy.fetchItemAspects
bidkit commerce taxonomy fetch-item-aspects CATEGORY-TREE-ID --format json
# commerce_taxonomy.getCategorySubtree
bidkit commerce taxonomy get-category-subtree CATEGORY-TREE-ID --category-id VALUE --format json
# commerce_taxonomy.getCategorySuggestions
bidkit commerce taxonomy get-category-suggestions CATEGORY-TREE-ID --q VALUE --format json
# commerce_taxonomy.getCategoryTree
bidkit commerce taxonomy get-category-tree CATEGORY-TREE-ID --format json
# commerce_taxonomy.getCompatibilityProperties
bidkit commerce taxonomy get-compatibility-properties CATEGORY-TREE-ID --category-id VALUE --format json
# commerce_taxonomy.getCompatibilityPropertyValues
bidkit commerce taxonomy get-compatibility-property-values CATEGORY-TREE-ID --compatibility-property VALUE --category-id VALUE --format json
# commerce_taxonomy.getDefaultCategoryTreeId
bidkit commerce taxonomy get-default-category-tree-id --marketplace-id VALUE --format json
# commerce_taxonomy.getExpiredCategories
bidkit commerce taxonomy get-expired-categories CATEGORY-TREE-ID --format json
# commerce_taxonomy.getItemAspectsForCategory
bidkit commerce taxonomy get-item-aspects-for-category CATEGORY-TREE-ID --category-id VALUE --format json
```

More (including execute examples with the required safety flags): `bidkit api examples <service>.<operationId>`.

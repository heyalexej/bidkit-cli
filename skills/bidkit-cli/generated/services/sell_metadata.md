# Metadata API

- **Service key:** `sell_metadata`
- **CLI:** `bidkit sell metadata`
- **Version:** v1.13.0
- **Base path:** `/sell/metadata/v1`  ·  **Subdomain:** `api`
- **Auth scheme:** `Bearer`  ·  **Requires signature:** False
- **Source spec:** `sell_metadata_v1_oas3.json`
- **Operations:** 28

Inspect any operation's full metadata or schema without a network call:

```bash
bidkit api describe sell_metadata.OPERATION_ID
bidkit api schema sell_metadata.OPERATION_ID request
```

| Operation key | Method | Path | Risk | Summary |
|---|---|---|---|---|
| `sell_metadata.getAutomotivePartsCompatibilityPolicies` | GET | `/marketplace/{marketplace_id}/get_automotive_parts_compatibility_policies` | read | This method returns the eBay policies that define how to list automotive parts compatibili |
| `sell_metadata.getCategoryPolicies` | GET | `/marketplace/{marketplace_id}/get_category_policies` | read | This method returns eBay category policy metadata for all leaf categories on the specified |
| `sell_metadata.getClassifiedAdPolicies` | GET | `/marketplace/{marketplace_id}/get_classified_ad_policies` | read | This method returns eBay classified ad policy metadata for all leaf categories on the spec |
| `sell_metadata.getCompatibilitiesBySpecification` | POST | `/compatibilities/get_compatibilities_by_specification` | unknown | This method is used to retrieve all compatible application name-value pairs for a part bas |
| `sell_metadata.getCompatibilityPropertyNames` | POST | `/compatibilities/get_compatibility_property_names` | unknown | This method is used to retrieve product compatibility property names for the specified com |
| `sell_metadata.getCompatibilityPropertyValues` | POST | `/compatibilities/get_compatibility_property_values` | unknown | This method is used to retrieve product compatibility property values associated with a si |
| `sell_metadata.getCurrencies` | GET | `/marketplace/{marketplace_id}/get_currencies` | read | This method returns the default currency used by the eBay marketplace specified in the req |
| `sell_metadata.getExcludeShippingLocations` | GET | `/shipping/marketplace/{marketplace_id}/get_exclude_shipping_locations` | read | This method retrieves a list of locations that the seller can use as excluded shipping loc |
| `sell_metadata.getExtendedProducerResponsibilityPolicies` | GET | `/marketplace/{marketplace_id}/get_extended_producer_responsibility_policies` | read | This method returns the Extended Producer Responsibility policies for one, multiple, or al |
| `sell_metadata.getHandlingTimes` | GET | `/shipping/marketplace/{marketplace_id}/get_handling_times` | read | This method retrieves a list of supported handling times for the specified marketplace. Th |
| `sell_metadata.getHazardousMaterialsLabels` | GET | `/marketplace/{marketplace_id}/get_hazardous_materials_labels` | read | This method returns hazardous materials label information for the specified eBay marketpla |
| `sell_metadata.getItemConditionPolicies` | GET | `/marketplace/{marketplace_id}/get_item_condition_policies` | read | This method returns item condition metadata on one, multiple, or all eBay categories on an |
| `sell_metadata.getListingStructurePolicies` | GET | `/marketplace/{marketplace_id}/get_listing_structure_policies` | read | This method returns the eBay policies that define the allowed listing structures for the c |
| `sell_metadata.getListingTypePolicies` | GET | `/marketplace/{marketplace_id}/get_listing_type_policies` | read | This method returns eBay listing type policy metadata for all leaf categories on the speci |
| `sell_metadata.getMinimumListingPricePolicies` | GET | `/marketplace/{marketplace_id}/get_minimum_listing_price_policies` | read | This method returns minimum listing price policies for supported types of listings on a sp |
| `sell_metadata.getMotorsListingPolicies` | GET | `/marketplace/{marketplace_id}/get_motors_listing_policies` | read | This method returns eBay Motors policy metadata for all leaf categories on the specified m |
| `sell_metadata.getMultiCompatibilityPropertyValues` | POST | `/compatibilities/get_multi_compatibility_property_values` | unknown | This method is used to retrieve product compatibility property values associated with mult |
| `sell_metadata.getNegotiatedPricePolicies` | GET | `/marketplace/{marketplace_id}/get_negotiated_price_policies` | read | This method returns the eBay policies that define the supported negotiated price features  |
| `sell_metadata.getProductCompatibilities` | POST | `/compatibilities/get_product_compatibilities` | unknown | This method is used to retrieve all available item compatibility details for the specified |
| `sell_metadata.getProductSafetyLabels` | GET | `/marketplace/{marketplace_id}/get_product_safety_labels` | read | This method returns product safety label information for the specified eBay marketplace. T |
| `sell_metadata.getRegulatoryPolicies` | GET | `/marketplace/{marketplace_id}/get_regulatory_policies` | read | This method returns regulatory policies for one, multiple, or all eBay categories in an eB |
| `sell_metadata.getReturnPolicies` | GET | `/marketplace/{marketplace_id}/get_return_policies` | read | This method returns the eBay policies that define whether or not you must include a return |
| `sell_metadata.getSalesTaxJurisdictions` | GET | `/country/{countryCode}/sales_tax_jurisdiction` | read | This method retrieves all sales-tax jurisdictions for the country specified in the country |
| `sell_metadata.getShippingCarriers` | GET | `/shipping/marketplace/{marketplace_id}/get_shipping_carriers` | read | This method retrieves a list of supported shipping carriers for the specified marketplace. |
| `sell_metadata.getShippingLocations` | GET | `/shipping/marketplace/{marketplace_id}/get_shipping_locations` | read | This method retrieves a list of supported shipping locations for the specified marketplace |
| `sell_metadata.getShippingPolicies` | GET | `/marketplace/{marketplace_id}/get_shipping_policies` | read | This method returns eBay shipping policy metadata for all leaf categories on the specified |
| `sell_metadata.getShippingServices` | GET | `/shipping/marketplace/{marketplace_id}/get_shipping_services` | read | This method retrieves a list of shipping services supported for the specified marketplace, |
| `sell_metadata.getSiteVisibilityPolicies` | GET | `/marketplace/{marketplace_id}/get_site_visibility_policies` | read | This method returns eBay international site visibility policy metadata for all leaf catego |

Command path prefix: `bidkit sell metadata <operation>`.

## Examples

```bash
# sell_metadata.getAutomotivePartsCompatibilityPolicies
bidkit sell metadata get-automotive-parts-compatibility-policies MARKETPLACE-ID --format json
# sell_metadata.getCategoryPolicies
bidkit sell metadata get-category-policies MARKETPLACE-ID --format json
# sell_metadata.getClassifiedAdPolicies
bidkit sell metadata get-classified-ad-policies MARKETPLACE-ID --format json
# sell_metadata.getCompatibilitiesBySpecification
bidkit sell metadata get-compatibilities-by-specification --body @request.json --format json --dry-run
# sell_metadata.getCompatibilityPropertyNames
bidkit sell metadata get-compatibility-property-names --body @request.json --format json --dry-run
# sell_metadata.getCompatibilityPropertyValues
bidkit sell metadata get-compatibility-property-values --body @request.json --format json --dry-run
# sell_metadata.getCurrencies
bidkit sell metadata get-currencies MARKETPLACE-ID --format json
# sell_metadata.getExcludeShippingLocations
bidkit sell metadata get-exclude-shipping-locations MARKETPLACE-ID --format json
# sell_metadata.getExtendedProducerResponsibilityPolicies
bidkit sell metadata get-extended-producer-responsibility-policies MARKETPLACE-ID --format json
# sell_metadata.getHandlingTimes
bidkit sell metadata get-handling-times MARKETPLACE-ID --format json
# sell_metadata.getHazardousMaterialsLabels
bidkit sell metadata get-hazardous-materials-labels MARKETPLACE-ID --format json
# sell_metadata.getItemConditionPolicies
bidkit sell metadata get-item-condition-policies MARKETPLACE-ID --format json
# sell_metadata.getListingStructurePolicies
bidkit sell metadata get-listing-structure-policies MARKETPLACE-ID --format json
# sell_metadata.getListingTypePolicies
bidkit sell metadata get-listing-type-policies MARKETPLACE-ID --format json
# sell_metadata.getMinimumListingPricePolicies
bidkit sell metadata get-minimum-listing-price-policies MARKETPLACE-ID --format json
# sell_metadata.getMotorsListingPolicies
bidkit sell metadata get-motors-listing-policies MARKETPLACE-ID --format json
# sell_metadata.getMultiCompatibilityPropertyValues
bidkit sell metadata get-multi-compatibility-property-values --body @request.json --format json --dry-run
# sell_metadata.getNegotiatedPricePolicies
bidkit sell metadata get-negotiated-price-policies MARKETPLACE-ID --format json
# sell_metadata.getProductCompatibilities
bidkit sell metadata get-product-compatibilities --body @request.json --format json --dry-run
# sell_metadata.getProductSafetyLabels
bidkit sell metadata get-product-safety-labels MARKETPLACE-ID --format json
# sell_metadata.getRegulatoryPolicies
bidkit sell metadata get-regulatory-policies MARKETPLACE-ID --format json
# sell_metadata.getReturnPolicies
bidkit sell metadata get-return-policies MARKETPLACE-ID --format json
# sell_metadata.getSalesTaxJurisdictions
bidkit sell metadata get-sales-tax-jurisdictions COUNTRY-CODE --format json
# sell_metadata.getShippingCarriers
bidkit sell metadata get-shipping-carriers MARKETPLACE-ID --format json
# sell_metadata.getShippingLocations
bidkit sell metadata get-shipping-locations MARKETPLACE-ID --format json
# sell_metadata.getShippingPolicies
bidkit sell metadata get-shipping-policies MARKETPLACE-ID --format json
# sell_metadata.getShippingServices
bidkit sell metadata get-shipping-services MARKETPLACE-ID --format json
# sell_metadata.getSiteVisibilityPolicies
bidkit sell metadata get-site-visibility-policies MARKETPLACE-ID --format json
```

More (including execute examples with the required safety flags): `bidkit api examples <service>.<operationId>`.

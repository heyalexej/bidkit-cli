# Marketing API

- **Service key:** `sell_marketing`
- **CLI:** `bidkit sell marketing`
- **Version:** v1.22.4
- **Base path:** `/sell/marketing/v1`  ·  **Subdomain:** `api`
- **Auth scheme:** `Bearer`  ·  **Requires signature:** False
- **Source spec:** `sell_marketing_v1_oas3.json`
- **Operations:** 80

Inspect any operation's full metadata or schema without a network call:

```bash
bidkit api describe sell_marketing.OPERATION_ID
bidkit api schema sell_marketing.OPERATION_ID request
```

| Operation key | Method | Path | Risk | Summary |
|---|---|---|---|---|
| `sell_marketing.bulkCreateAdsByInventoryReference` | POST | `/ad_campaign/{campaign_id}/bulk_create_ads_by_inventory_reference` | unknown | This method adds multiple listings that are managed with the Inventory API to an existing  |
| `sell_marketing.bulkCreateAdsByListingId` | POST | `/ad_campaign/{campaign_id}/bulk_create_ads_by_listing_id` | unknown | This method adds multiple listings to an existing Promoted Listings campaign using listing |
| `sell_marketing.bulkCreateKeyword` | POST | `/ad_campaign/{campaign_id}/bulk_create_keyword` | unknown | This method adds keywords, in bulk, to an existing priority strategy ad group in a campaig |
| `sell_marketing.bulkCreateNegativeKeyword` | POST | `/bulk_create_negative_keyword` | unknown | This method adds negative keywords, in bulk, to an existing ad group in a priority strateg |
| `sell_marketing.bulkDeleteAdsByInventoryReference` | POST | `/ad_campaign/{campaign_id}/bulk_delete_ads_by_inventory_reference` | unknown | This method works with listings created with the Inventory API . The method deletes a set  |
| `sell_marketing.bulkDeleteAdsByListingId` | POST | `/ad_campaign/{campaign_id}/bulk_delete_ads_by_listing_id` | unknown | This method works with listing IDs created with either the Trading API or the Inventory AP |
| `sell_marketing.bulkUpdateAdsBidByInventoryReference` | POST | `/ad_campaign/{campaign_id}/bulk_update_ads_bid_by_inventory_reference` | unknown | This method works with listings created with either the Trading API or the Inventory API . |
| `sell_marketing.bulkUpdateAdsBidByListingId` | POST | `/ad_campaign/{campaign_id}/bulk_update_ads_bid_by_listing_id` | unknown | This method works with listings created with either the Trading API or the Inventory API . |
| `sell_marketing.bulkUpdateAdsStatus` | POST | `/ad_campaign/{campaign_id}/bulk_update_ads_status` | unknown | Note: This method is only available for select partners who have been approved for the pri |
| `sell_marketing.bulkUpdateAdsStatusByListingId` | POST | `/ad_campaign/{campaign_id}/bulk_update_ads_status_by_listing_id` | unknown | The method updates the status of ads in bulk, based on listing ID values. Specify the camp |
| `sell_marketing.bulkUpdateKeyword` | POST | `/ad_campaign/{campaign_id}/bulk_update_keyword` | unknown | This method updates the bids and statuses of keywords, in bulk, for an existing priority s |
| `sell_marketing.bulkUpdateNegativeKeyword` | POST | `/bulk_update_negative_keyword` | unknown | This method updates the statuses of existing negative keywords, in bulk. Specify the negat |
| `sell_marketing.cloneCampaign` | POST | `/ad_campaign/{campaign_id}/clone` | unknown | This method clones (makes a copy of) the specified campaign's campaign criterion . The cam |
| `sell_marketing.createAdByListingId` | POST | `/ad_campaign/{campaign_id}/ad` | unknown | This method adds a listing to an existing Promoted Listings campaign using a listingId val |
| `sell_marketing.createAdGroup` | POST | `/ad_campaign/{campaign_id}/ad_group` | unknown | This method adds an ad group to an existing priority strategy campaign that uses manual ta |
| `sell_marketing.createAdsByInventoryReference` | POST | `/ad_campaign/{campaign_id}/create_ads_by_inventory_reference` | unknown | This method adds a listing that is managed with the Inventory API to an existing Promoted  |
| `sell_marketing.createCampaign` | POST | `/ad_campaign` | unknown | This method can be used to create a Promoted Listings general, priority, or offsite campai |
| `sell_marketing.createEmailCampaign` | POST | `/email_campaign` | unknown | This method creates a new email campaign. An eBay store owner can create six different typ |
| `sell_marketing.createItemPriceMarkdownPromotion` | POST | `/item_price_markdown` | unknown | Note: As of July 8th 2024, promotions are now being referred to as discounts on Seller Hub |
| `sell_marketing.createItemPromotion` | POST | `/item_promotion` | unknown | Note: As of July 8th 2024, promotions are now being referred to as discounts on Seller Hub |
| `sell_marketing.createKeyword` | POST | `/ad_campaign/{campaign_id}/keyword` | unknown | This method creates keywords using a specified campaign ID for an existing priority strate |
| `sell_marketing.createNegativeKeyword` | POST | `/negative_keyword` | unknown | This method adds a negative keyword to an existing ad group in a priority strategy campaig |
| `sell_marketing.createReportTask` | POST | `/ad_report_task` | unknown | This method creates a report task , which generates a Promoted Listings report based on th |
| `sell_marketing.deleteAd` | DELETE | `/ad_campaign/{campaign_id}/ad/{ad_id}` | destructive | This method removes the specified ad from the specified campaign. Pass the ID of the ad to |
| `sell_marketing.deleteAdsByInventoryReference` | POST | `/ad_campaign/{campaign_id}/delete_ads_by_inventory_reference` | unknown | This method works with listings that are managed with the Inventory API . The method delet |
| `sell_marketing.deleteCampaign` | DELETE | `/ad_campaign/{campaign_id}` | destructive | This method deletes the campaign specified by the campaign_id query parameter. Note: You c |
| `sell_marketing.deleteEmailCampaign` | DELETE | `/email_campaign/{email_campaign_id}` | destructive | This method deletes the email campaign specified by the email_campaign_id path parameter.  |
| `sell_marketing.deleteItemPriceMarkdownPromotion` | DELETE | `/item_price_markdown/{promotion_id}` | destructive | Note: As of July 8th 2024, promotions are now being referred to as discounts on Seller Hub |
| `sell_marketing.deleteItemPromotion` | DELETE | `/item_promotion/{promotion_id}` | destructive | Note: As of July 8th 2024, promotions are now being referred to as discounts on Seller Hub |
| `sell_marketing.deleteReportTask` | DELETE | `/ad_report_task/{report_task_id}` | destructive | This call deletes the report task specified by the report_task_id path parameter. This met |
| `sell_marketing.endCampaign` | POST | `/ad_campaign/{campaign_id}/end` | unknown | This method ends an active ( RUNNING ) or paused campaign. Specify the campaign you want t |
| `sell_marketing.findCampaignByAdReference` | GET | `/ad_campaign/find_campaign_by_ad_reference` | read | This method retrieves the campaigns containing the listing that is specified using either  |
| `sell_marketing.getAd` | GET | `/ad_campaign/{campaign_id}/ad/{ad_id}` | read | This method retrieves the specified ad from the specified campaign. In the request, supply |
| `sell_marketing.getAdGroup` | GET | `/ad_campaign/{campaign_id}/ad_group/{ad_group_id}` | read | This method retrieves the details of a specified ad group, such as the ad group’s default  |
| `sell_marketing.getAdGroups` | GET | `/ad_campaign/{campaign_id}/ad_group` | read | This method retrieves ad groups for the specified campaign. Each campaign can only have on |
| `sell_marketing.getAds` | GET | `/ad_campaign/{campaign_id}/ad` | read | This method retrieves Promoted Listings ads that are associated with listings created with |
| `sell_marketing.getAdsByInventoryReference` | GET | `/ad_campaign/{campaign_id}/get_ads_by_inventory_reference` | read | This method retrieves Promoted Listings ads associated with listings that are managed with |
| `sell_marketing.getAudiences` | GET | `/email_campaign/audience` | read | This method retrieves all available email newsletter audiences for the email campaign type |
| `sell_marketing.getCampaign` | GET | `/ad_campaign/{campaign_id}` | read | This method retrieves the details of a single campaign, as specified with the campaign_id  |
| `sell_marketing.getCampaignByName` | GET | `/ad_campaign/get_campaign_by_name` | read | This method retrieves the details of a single campaign, as specified with the campaign_nam |
| `sell_marketing.getCampaigns` | GET | `/ad_campaign` | read | This method retrieves the details for all of the seller's defined campaigns. Request param |
| `sell_marketing.getEmailCampaign` | GET | `/email_campaign/{email_campaign_id}` | read | This method returns the details of a single email campaign specified by the email_campaign |
| `sell_marketing.getEmailCampaigns` | GET | `/email_campaign` | read | This method retrieves a list of email campaigns from a seller's eBay store. Users can filt |
| `sell_marketing.getEmailPreview` | GET | `/email_campaign/{email_campaign_id}/email_preview` | read | This method returns a preview of the email sent by the email campaign indicated by the ema |
| `sell_marketing.getEmailReport` | GET | `/email_campaign/report` | read | This method returns the seller's email campaign performance report for a time period speci |
| `sell_marketing.getItemPriceMarkdownPromotion` | GET | `/item_price_markdown/{promotion_id}` | read | Note: As of July 8th 2024, promotions are now being referred to as discounts on Seller Hub |
| `sell_marketing.getItemPromotion` | GET | `/item_promotion/{promotion_id}` | read | Note: As of July 8th 2024, promotions are now being referred to as discounts on Seller Hub |
| `sell_marketing.getKeyword` | GET | `/ad_campaign/{campaign_id}/keyword/{keyword_id}` | read | This method retrieves details on a specific keyword from an ad group within a priority str |
| `sell_marketing.getKeywords` | GET | `/ad_campaign/{campaign_id}/keyword` | read | This method can be used to retrieve all of the keywords for ad groups in priority strategy |
| `sell_marketing.getListingSet` | GET | `/promotion/{promotion_id}/get_listing_set` | read | Note: As of July 8th 2024, promotions are now being referred to as discounts on Seller Hub |
| `sell_marketing.getNegativeKeyword` | GET | `/negative_keyword/{negative_keyword_id}` | read | This method retrieves details on a specific negative keyword. In the request, specify the  |
| `sell_marketing.getNegativeKeywords` | GET | `/negative_keyword` | read | This method can be used to retrieve all of the negative keywords for ad groups in priority |
| `sell_marketing.getPromotionReports` | GET | `/promotion_report` | read | Note: As of July 8th 2024, promotions are now being referred to as discounts on Seller Hub |
| `sell_marketing.getPromotionSummaryReport` | GET | `/promotion_summary_report` | read | Note: As of July 8th 2024, promotions are now being referred to as discounts on Seller Hub |
| `sell_marketing.getPromotions` | GET | `/promotion` | read | Note: As of July 8th 2024, promotions are now being referred to as discounts on Seller Hub |
| `sell_marketing.getReport` | GET | `/ad_report/{report_id}` | read | This call downloads the report as specified by the report_id path parameter. Call createRe |
| `sell_marketing.getReportMetadata` | GET | `/ad_report_metadata` | read | This call retrieves information that details the fields used in each of the Promoted Listi |
| `sell_marketing.getReportMetadataForReportType` | GET | `/ad_report_metadata/{report_type}` | read | This call retrieves metadata that details the fields used by a specific Promoted Listings  |
| `sell_marketing.getReportTask` | GET | `/ad_report_task/{report_task_id}` | read | This call returns the details of a specific Promoted Listings report task, as specified by |
| `sell_marketing.getReportTasks` | GET | `/ad_report_task` | read | This method returns information on all the existing report tasks related to a seller. Use  |
| `sell_marketing.pauseCampaign` | POST | `/ad_campaign/{campaign_id}/pause` | unknown | This method pauses an active (RUNNING) campaign. You can restart the campaign by calling r |
| `sell_marketing.pausePromotion` | POST | `/promotion/{promotion_id}/pause` | unknown | Note: As of July 8th 2024, promotions are now being referred to as discounts on Seller Hub |
| `sell_marketing.resumeCampaign` | POST | `/ad_campaign/{campaign_id}/resume` | unknown | This method resumes a paused campaign, as long as its end date is in the future. Supply th |
| `sell_marketing.resumePromotion` | POST | `/promotion/{promotion_id}/resume` | unknown | Note: As of July 8th 2024, promotions are now being referred to as discounts on Seller Hub |
| `sell_marketing.suggestBids` | POST | `/ad_campaign/{campaign_id}/ad_group/{ad_group_id}/suggest_bids` | unknown | This method allows sellers to retrieve the suggested bids for input keywords and match typ |
| `sell_marketing.suggestBudget` | GET | `/ad_campaign/suggest_budget` | read | Note: This method is only supported for Promoted Offsite campaigns. Sellers can use the ge |
| `sell_marketing.suggestItems` | GET | `/ad_campaign/{campaign_id}/suggest_items` | read | This method allows sellers to obtain ideas for listings, which can be targeted for Promote |
| `sell_marketing.suggestKeywords` | POST | `/ad_campaign/{campaign_id}/ad_group/{ad_group_id}/suggest_keywords` | unknown | This method allows sellers to retrieve a list of keyword ideas to be targeted for Promoted |
| `sell_marketing.suggestMaxCpc` | POST | `/ad_campaign/suggest_max_cpc` | unknown | Note: This method is only supported for smart targeting priority strategy campaigns. Selle |
| `sell_marketing.updateAdGroup` | PUT | `/ad_campaign/{campaign_id}/ad_group/{ad_group_id}` | write | This method updates the ad group associated with a campaign. With this method, you can mod |
| `sell_marketing.updateAdRateStrategy` | POST | `/ad_campaign/{campaign_id}/update_ad_rate_strategy` | unknown | This method updates the ad rate strategy for an existing rules-based general strategy ad c |
| `sell_marketing.updateBid` | POST | `/ad_campaign/{campaign_id}/ad/{ad_id}/update_bid` | unknown | This method updates the bid percentage (also known as the "ad rate") for the specified ad  |
| `sell_marketing.updateBiddingStrategy` | POST | `/ad_campaign/{campaign_id}/update_bidding_strategy` | unknown | This method allows sellers to change the bidding strategy for a specified Cost Per Click ( |
| `sell_marketing.updateCampaignBudget` | POST | `/ad_campaign/{campaign_id}/update_campaign_budget` | unknown | This method updates the daily budget for a priority strategy campaign that uses the Cost P |
| `sell_marketing.updateCampaignIdentification` | POST | `/ad_campaign/{campaign_id}/update_campaign_identification` | unknown | This method can be used to change the name of a campaign, as well as modify the start or e |
| `sell_marketing.updateEmailCampaign` | PUT | `/email_campaign/{email_campaign_id}` | write | This method lets users update an existing email campaign. Pass the emailCampaignId in the  |
| `sell_marketing.updateItemPriceMarkdownPromotion` | PUT | `/item_price_markdown/{promotion_id}` | write | Note: As of July 8th 2024, promotions are now being referred to as discounts on Seller Hub |
| `sell_marketing.updateItemPromotion` | PUT | `/item_promotion/{promotion_id}` | write | Note: As of July 8th 2024, promotions are now being referred to as discounts on Seller Hub |
| `sell_marketing.updateKeyword` | PUT | `/ad_campaign/{campaign_id}/keyword/{keyword_id}` | write | This method updates keywords using a campaign ID and keyword ID for an existing priority s |
| `sell_marketing.updateNegativeKeyword` | PUT | `/negative_keyword/{negative_keyword_id}` | write | This method updates the status of an existing negative keyword. Specify the negative_keywo |

Command path prefix: `bidkit sell marketing <operation>`.

## Examples

```bash
# sell_marketing.bulkCreateAdsByInventoryReference
bidkit sell marketing bulk-create-ads-by-inventory-reference CAMPAIGN-ID --body @request.json --format json --dry-run
# sell_marketing.bulkCreateAdsByListingId
bidkit sell marketing bulk-create-ads-by-listing-id CAMPAIGN-ID --body @request.json --format json --dry-run
# sell_marketing.bulkCreateKeyword
bidkit sell marketing bulk-create-keyword CAMPAIGN-ID --body @request.json --format json --dry-run
# sell_marketing.bulkCreateNegativeKeyword
bidkit sell marketing bulk-create-negative-keyword --body @request.json --format json --dry-run
# sell_marketing.bulkDeleteAdsByInventoryReference
bidkit sell marketing bulk-delete-ads-by-inventory-reference CAMPAIGN-ID --body @request.json --format json --dry-run
# sell_marketing.bulkDeleteAdsByListingId
bidkit sell marketing bulk-delete-ads-by-listing-id CAMPAIGN-ID --body @request.json --format json --dry-run
# sell_marketing.bulkUpdateAdsBidByInventoryReference
bidkit sell marketing bulk-update-ads-bid-by-inventory-reference CAMPAIGN-ID --body @request.json --format json --dry-run
# sell_marketing.bulkUpdateAdsBidByListingId
bidkit sell marketing bulk-update-ads-bid-by-listing-id CAMPAIGN-ID --body @request.json --format json --dry-run
# sell_marketing.bulkUpdateAdsStatus
bidkit sell marketing bulk-update-ads-status CAMPAIGN-ID --body @request.json --format json --dry-run
# sell_marketing.bulkUpdateAdsStatusByListingId
bidkit sell marketing bulk-update-ads-status-by-listing-id CAMPAIGN-ID --body @request.json --format json --dry-run
# sell_marketing.bulkUpdateKeyword
bidkit sell marketing bulk-update-keyword CAMPAIGN-ID --body @request.json --format json --dry-run
# sell_marketing.bulkUpdateNegativeKeyword
bidkit sell marketing bulk-update-negative-keyword --body @request.json --format json --dry-run
# sell_marketing.cloneCampaign
bidkit sell marketing clone-campaign CAMPAIGN-ID --body @request.json --format json --dry-run
# sell_marketing.createAdByListingId
bidkit sell marketing create-ad-by-listing-id CAMPAIGN-ID --body @request.json --format json --dry-run
# sell_marketing.createAdGroup
bidkit sell marketing create-ad-group CAMPAIGN-ID --body @request.json --format json --dry-run
# sell_marketing.createAdsByInventoryReference
bidkit sell marketing create-ads-by-inventory-reference CAMPAIGN-ID --body @request.json --format json --dry-run
# sell_marketing.createCampaign
bidkit sell marketing create-campaign --body @request.json --format json --dry-run
# sell_marketing.createEmailCampaign
bidkit sell marketing create-email-campaign --body @request.json --format json --dry-run
# sell_marketing.createItemPriceMarkdownPromotion
bidkit sell marketing create-item-price-markdown-promotion --body @request.json --format json --dry-run
# sell_marketing.createItemPromotion
bidkit sell marketing create-item-promotion --body @request.json --format json --dry-run
# sell_marketing.createKeyword
bidkit sell marketing create-keyword CAMPAIGN-ID --body @request.json --format json --dry-run
# sell_marketing.createNegativeKeyword
bidkit sell marketing create-negative-keyword --body @request.json --format json --dry-run
# sell_marketing.createReportTask
bidkit sell marketing create-report-task --body @request.json --format json --dry-run
# sell_marketing.deleteAd
bidkit sell marketing delete-ad AD-ID CAMPAIGN-ID --format json --dry-run
# sell_marketing.deleteAdsByInventoryReference
bidkit sell marketing delete-ads-by-inventory-reference CAMPAIGN-ID --body @request.json --format json --dry-run
# sell_marketing.deleteCampaign
bidkit sell marketing delete-campaign CAMPAIGN-ID --format json --dry-run
# sell_marketing.deleteEmailCampaign
bidkit sell marketing delete-email-campaign EMAIL-CAMPAIGN-ID --format json --dry-run
# sell_marketing.deleteItemPriceMarkdownPromotion
bidkit sell marketing delete-item-price-markdown-promotion PROMOTION-ID --format json --dry-run
# sell_marketing.deleteItemPromotion
bidkit sell marketing delete-item-promotion PROMOTION-ID --format json --dry-run
# sell_marketing.deleteReportTask
bidkit sell marketing delete-report-task REPORT-TASK-ID --format json --dry-run
# sell_marketing.endCampaign
bidkit sell marketing end-campaign CAMPAIGN-ID --format json --dry-run
# sell_marketing.findCampaignByAdReference
bidkit sell marketing find-campaign-by-ad-reference --format json
# sell_marketing.getAd
bidkit sell marketing get-ad AD-ID CAMPAIGN-ID --format json
# sell_marketing.getAdGroup
bidkit sell marketing get-ad-group AD-GROUP-ID CAMPAIGN-ID --format json
# sell_marketing.getAdGroups
bidkit sell marketing get-ad-groups CAMPAIGN-ID --limit 30 --format json
# sell_marketing.getAds
bidkit sell marketing get-ads CAMPAIGN-ID --limit 30 --format json
# sell_marketing.getAdsByInventoryReference
bidkit sell marketing get-ads-by-inventory-reference CAMPAIGN-ID --inventory-reference-id VALUE --inventory-reference-type VALUE --format json
# sell_marketing.getAudiences
bidkit sell marketing get-audiences --email-campaign-type VALUE --limit 30 --format json
# sell_marketing.getCampaign
bidkit sell marketing get-campaign CAMPAIGN-ID --format json
# sell_marketing.getCampaignByName
bidkit sell marketing get-campaign-by-name --campaign-name VALUE --format json
# sell_marketing.getCampaigns
bidkit sell marketing get-campaigns --limit 30 --format json
# sell_marketing.getEmailCampaign
bidkit sell marketing get-email-campaign EMAIL-CAMPAIGN-ID --format json
# sell_marketing.getEmailCampaigns
bidkit sell marketing get-email-campaigns --limit 30 --format json
# sell_marketing.getEmailPreview
bidkit sell marketing get-email-preview EMAIL-CAMPAIGN-ID --format json
# sell_marketing.getEmailReport
bidkit sell marketing get-email-report --end-date VALUE --start-date VALUE --format json
# sell_marketing.getItemPriceMarkdownPromotion
bidkit sell marketing get-item-price-markdown-promotion PROMOTION-ID --format json
# sell_marketing.getItemPromotion
bidkit sell marketing get-item-promotion PROMOTION-ID --format json
# sell_marketing.getKeyword
bidkit sell marketing get-keyword CAMPAIGN-ID KEYWORD-ID --format json
# sell_marketing.getKeywords
bidkit sell marketing get-keywords CAMPAIGN-ID --limit 30 --format json
# sell_marketing.getListingSet
bidkit sell marketing get-listing-set PROMOTION-ID --limit 30 --format json
# sell_marketing.getNegativeKeyword
bidkit sell marketing get-negative-keyword NEGATIVE-KEYWORD-ID --format json
# sell_marketing.getNegativeKeywords
bidkit sell marketing get-negative-keywords --ad-group-ids VALUE --limit 30 --format json
# sell_marketing.getPromotionReports
bidkit sell marketing get-promotion-reports --marketplace-id VALUE --limit 30 --format json
# sell_marketing.getPromotionSummaryReport
bidkit sell marketing get-promotion-summary-report --marketplace-id VALUE --format json
# sell_marketing.getPromotions
bidkit sell marketing get-promotions --marketplace-id VALUE --limit 30 --format json
# sell_marketing.getReport
bidkit sell marketing get-report REPORT-ID --format json
# sell_marketing.getReportMetadata
bidkit sell marketing get-report-metadata --format json
# sell_marketing.getReportMetadataForReportType
bidkit sell marketing get-report-metadata-for-report-type REPORT-TYPE --format json
# sell_marketing.getReportTask
bidkit sell marketing get-report-task REPORT-TASK-ID --format json
# sell_marketing.getReportTasks
bidkit sell marketing get-report-tasks --limit 30 --format json
# sell_marketing.pauseCampaign
bidkit sell marketing pause-campaign CAMPAIGN-ID --format json --dry-run
# sell_marketing.pausePromotion
bidkit sell marketing pause-promotion PROMOTION-ID --format json --dry-run
# sell_marketing.resumeCampaign
bidkit sell marketing resume-campaign CAMPAIGN-ID --format json --dry-run
# sell_marketing.resumePromotion
bidkit sell marketing resume-promotion PROMOTION-ID --format json --dry-run
# sell_marketing.suggestBids
bidkit sell marketing suggest-bids AD-GROUP-ID CAMPAIGN-ID --body @request.json --format json --dry-run
# sell_marketing.suggestBudget
bidkit sell marketing suggest-budget --format json
# sell_marketing.suggestItems
bidkit sell marketing suggest-items CAMPAIGN-ID --limit 30 --format json
# sell_marketing.suggestKeywords
bidkit sell marketing suggest-keywords AD-GROUP-ID CAMPAIGN-ID --body @request.json --format json --dry-run
# sell_marketing.suggestMaxCpc
bidkit sell marketing suggest-max-cpc --body @request.json --format json --dry-run
# sell_marketing.updateAdGroup
bidkit sell marketing update-ad-group AD-GROUP-ID CAMPAIGN-ID --body @request.json --format json --dry-run
# sell_marketing.updateAdRateStrategy
bidkit sell marketing update-ad-rate-strategy CAMPAIGN-ID --body @request.json --format json --dry-run
# sell_marketing.updateBid
bidkit sell marketing update-bid AD-ID CAMPAIGN-ID --body @request.json --format json --dry-run
# sell_marketing.updateBiddingStrategy
bidkit sell marketing update-bidding-strategy CAMPAIGN-ID --body @request.json --format json --dry-run
# sell_marketing.updateCampaignBudget
bidkit sell marketing update-campaign-budget CAMPAIGN-ID --body @request.json --format json --dry-run
# sell_marketing.updateCampaignIdentification
bidkit sell marketing update-campaign-identification CAMPAIGN-ID --body @request.json --format json --dry-run
# sell_marketing.updateEmailCampaign
bidkit sell marketing update-email-campaign EMAIL-CAMPAIGN-ID --body @request.json --format json --dry-run
# sell_marketing.updateItemPriceMarkdownPromotion
bidkit sell marketing update-item-price-markdown-promotion PROMOTION-ID --body @request.json --format json --dry-run
# sell_marketing.updateItemPromotion
bidkit sell marketing update-item-promotion PROMOTION-ID --body @request.json --format json --dry-run
# sell_marketing.updateKeyword
bidkit sell marketing update-keyword CAMPAIGN-ID KEYWORD-ID --body @request.json --format json --dry-run
# sell_marketing.updateNegativeKeyword
bidkit sell marketing update-negative-keyword NEGATIVE-KEYWORD-ID --body @request.json --format json --dry-run
```

More (including execute examples with the required safety flags): `bidkit api examples <service>.<operationId>`.

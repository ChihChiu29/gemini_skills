---
name: leasehackr-ev-deals
description: Scrapes and tracks the 10 cheapest EV lease deals for Northern California from Leasehackr, storing daily data in CACHE, generating HTML reports in OUTPUT, and reporting price variations.
---

# Leasehackr NorCal EV Lease Deal Tracker

This skill finds the 10 cheapest EV lease deals for Northern California from the Leasehackr Marketplace, caches the raw JSON data per day, performs historical price variation tracking, and generates an interactive HTML report in `OUTPUT/`.

## Workflow

1.  Run Tracker Script: Execute the python script:
    [leasehackr_ev_scraper.py](./scripts/leasehackr_ev_scraper.py)
2.  Duplicate Detection: If run twice on the same day, the script automatically logs a no-op statement and prints/renders the reports using the existing day's cache.
3.  Data & Output Generation:
    * Saves daily records to `CACHE/ev_deals_YYYY-MM-DD.json`.
    * Extracts monthly payments, DAS (due at signing), and term to calculate Effective Monthly Cost (Monthly + DAS/Term).
    * Generates a styled HTML report in `OUTPUT/ev_deals_report_YYYYMMDD_HHMMSS.html` containing both the top 10 EV deals table and historical price change analysis.

## Using the Script

To retrieve and track deals, run:

python skill_src/leasehackr-ev-deals/scripts/leasehackr_ev_scraper.py


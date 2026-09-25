---
name: leasehackr-ev-deals
description: Tracks the top 6 cheapest EV lease deals for Northern California from Leasehackr Pre-Negotiated Deals (PND), caching daily data and producing up to 90 days of historical reports in OUTPUT/leasehackr.
---

# Leasehackr NorCal EV Lease Deal Tracker

This skill finds the top 6 cheapest EV lease deals for Northern California directly from Leasehackr Pre-Negotiated Deals (PND), caches the daily data, and generates 90-day history tables in Markdown and HTML under `OUTPUT/leasehackr/`.

## Workflow

1. **Run Tracker Script**: Execute:
   ```cmd
   run_leasehackr_skill.bat
   ```
   or:
   ```powershell
   python skill_src/leasehackr-ev-deals/scripts/pnd_ev_deals_tracker.py
   ```
2. **Filtering & Extraction**:
   * Source: `https://pnd.leasehackr.com/r/California`
   * Filters: Location = "Northern California", Fuel Type = "EV"
   * Prices reflect standard advertised pricing (excluding conditional "First EV" discounts).
   * Extracts Upfront (DAS), Monthly payment, Lease term, and Allowed mileage per year.
3. **Daily Cache**:
   * Stored in `CACHE/leasehackr_pnd/pnd_ev_deals_YYYY-MM-DD.json`.
   * Reuses the cache if run multiple times within the same day.
4. **90-Day Output Reports**:
   * HTML report generated in `OUTPUT/leasehackr/leasehackr_ev_deals_report_YYYY-MM-DD.html`

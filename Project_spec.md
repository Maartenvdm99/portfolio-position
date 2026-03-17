# project_specs.md 
## 0) Product Summary

A **Portfolio Position Dashboard** for an energy company, built in Streamlit.

**Who uses it:** Energy company staff who need to view and analyze portfolio positions by day.

**What it does:** 
- Displays portfolio position data across multiple tabs (replicated from the Excel example)
- Allows users to select different dates to view data
- Allows exporting the ETPA tab as CSV

**Tech stack:**
- **Framework:** Streamlit (Python)
- **Data source:** Excel file (Dashboard portfolio position.xlsx) - will eventually move to database/CSV
- **Export format:** CSV

## 1) Pages & User Flows

### Main Dashboard Page
1. **Date selector button** at the top (dropdown or date picker)
2. **Multiple tabs** matching the Excel file structure:
   - Each tab shows a different portfolio position view
   - All tabs pulled from the Excel example
3. **ETPA tab specific:**
   - Has an "Export CSV" button
   - Button exports the current ETPA tab data as CSV file

## 2) Data Structure

**Source:** Dashboard portfolio position.xlsx
- Multiple sheets/tabs (need to confirm names from Excel)
- Each sheet has:
  - Columns (formatting, types, widths)
  - Rows of data
  - Possible formulas/calculations to replicate
  
**What needs copying:**
- ✅ All tabs/sheets from Excel
- ✅ All columns and formatting
- ✅ All formulas and calculations
- ✅ Column widths/layout

## 3) Features Required

1. **Date selector** - button at top to pick which day's data to view
2. **Tab navigation** - multiple views matching Excel tabs
3. **CSV export** - button in ETPA tab only
4. **Formatting** - match the Excel styling as closely as possible in Streamlit

## 4) Questions to Confirm

## 5) Out of Scope (for now)
- Database backend (using Excel as source)
- User authentication
- Real-time data updates
- Multiple users with different permissions

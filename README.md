# Chih's Antigravity CLI Skills

A collection of specialized expert skills for the Antigravity CLI.

## Workspace Structure

- **`skill_src/`**: Contains the source code for each skill. Use this directory if you want to modify the skills or link them for development.
- **`RELEASE/`**: Contains pre-packaged `.skill` files for easy distribution and installation.
- **`CACHE/`**: A local directory (ignored by git) where skills store persistent data like historical stock prices to reduce API calls.
- **`OUTPUT/`**: A local directory (ignored by git) where skills save their generated reports and artifacts.

## Available Skills

### 📈 Stock Trend & Lows Analyzer
Analyzes major U.S. stocks to find those trading near historical lows or experiencing recent sharp declines.
- **Features**: 4-column proximity analysis (3Y, 6M, 3M, 7D), trend tracking, and color-coded HTML reports.
- **Source**: `skill_src/stock-lows-analyzer/`

---

## Installation Instructions

### Option 1: Automated Developer Setup (Recommended for Windows)
If you are developing locally, you can use the provided PowerShell helper to automatically clean up any old directories and link all skills to both modern Antigravity and legacy environments:

```powershell
.\link_skills.ps1
```

### Option 2: Fast Installation from Release Package
To install all available skills from pre-packaged release files, run the following command in your terminal:

```powershell
antigravity skills install RELEASE/*.skill --scope workspace
```
*(For legacy environments, `jetski skills install RELEASE/*.skill --scope workspace` is also supported.)*

### Option 3: Manual Development / Linking
To manually link the stock analyzer skill to your workspace, run:

```powershell
antigravity skills link skill_src/stock-lows-analyzer --scope workspace
```
*(For legacy environments, use `jetski skills link skill_src/stock-lows-analyzer --scope workspace`.)*

## Requirements
Most scripts in this repository require Python. The Stock Analyzer specifically requires `yfinance`:
```bash
pip install yfinance
```

## Author
Created by Chih.

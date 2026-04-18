# Chih's Gemini CLI Skills

A collection of specialized expert skills for the Gemini CLI.

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

### Option 1: Fast Installation (Recommended)
To install all available skills from the latest releases, run the following command in your terminal from the project root:

```powershell
gemini skills install RELEASE/*.skill --scope workspace
```

### Option 2: Development / Linking
If you want to stay up-to-date with changes in the source code or contribute to development, link the skill instead:

```powershell
gemini skills link skill_src/stock-lows-analyzer --scope workspace
```

## Requirements
Most scripts in this repository require Python. The Stock Analyzer specifically requires `yfinance`:
```bash
pip install yfinance
```

## Author
Created by Chih.

# LiquidX Trading Terminal

LiquidX is a Python-based automated and semi-automated trading terminal designed to analyze and execute Inner Circle Trader (ICT) concepts on S&P 500 futures. It provides real-time market structure visualization, algorithmic backtesting, and live execution via the Topstep API.

## Core Features

- **ICT Engine (`ict_engine.py`)**: The brain of the operation. Detects Fair Value Gaps (FVGs), determines daily bias, calculates Power of 3 (PO3) levels, and evaluates market structure.
- **SMT Divergence**: Compares relative strength across S&P 500 (ES), Nasdaq (NQ), and Dow Jones (YM) to identify underlying market imbalances.
- **Backtester (`backtester.py`)**: A robust historical backtesting engine that simulates trading the ICT strategy across multiple timeframes (Daily, 1H, 5M).
- **Streamlit Terminal UI (`main.py`)**: A modern, dark-themed dashboard built with Streamlit and Plotly for visualizing setups and executing trades.
- **QuantX Connector (`broker_connector.py`)**: Handles live and simulated trade execution across multiple accounts utilizing the QuantX library for the Topstep API.

## Tech Stack

- **UI Framework**: [Streamlit](https://streamlit.io/)
- **Data Manipulation**: [pandas](https://pandas.pydata.org/), [NumPy](https://numpy.org/)
- **Charting**: [Plotly](https://plotly.com/)
- **API Integration**: [QuantX](https://github.com/quantDIY/QuantX) (Topstep API)
- **Environment Management**: `python-dotenv`

## Installation

1. **Clone the repository:**
   ```bash
   git clone <repository_url>
   cd <repository_directory>
   ```

2. **Set up a Python virtual environment (recommended):**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. **Install dependencies:**
   ```bash
   pip install pandas numpy plotly python-dotenv streamlit
   ```
   *(Note: The QuantX backend may have additional requirements depending on your specific setup.)*

4. **Configure your environment:**
   LiquidX requires a Topstep API key. Ensure your `.env` file in the `QuantX/backend/` directory is correctly configured with your `TOPSTEP_API_KEY` and other necessary credentials.

## Usage

### Running the Terminal UI

To launch the LiquidX Trading Terminal dashboard in your browser:

```bash
streamlit run main.py
```

### Running the Backtester

To simulate the trading strategy against historical data located in the `/tradingdata` folder:

```bash
python backtester.py
```

### Running Tests

To verify the core ICT engine logic:

```bash
python test_ict_engine.py
```

## Data Requirements

The application expects historical and real-time intraday `.csv` files provided by Barchart to be present in the `tradingdata/` directory. Files should follow prefixes indicating their instrument (e.g., `spx_`, `nqh26_`, `ymh26_`).
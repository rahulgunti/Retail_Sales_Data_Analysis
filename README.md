# Retail Sales Analysis

An end-to-end analysis of the [Online Retail II dataset on Kaggle](https://www.kaggle.com/datasets/mashlyn/online-retail-ii-uci). The project cleans the source data, analyzes revenue and customer/product performance, and generates an Excel workbook, CSV summaries, and Matplotlib charts.

## Questions explored

- How does revenue change month by month?
- Which countries contribute the most revenue?
- Which products lead by revenue?
- How many invoices, customers, and units are represented in the valid sales?
- How much data is removed or retained during cleaning?

## Dataset

Download the dataset from Kaggle. The source workbook contains the Online Retail II transactions; do not commit the downloaded dataset to GitHub.

1. Create a Kaggle account and accept any dataset terms shown on Kaggle.
2. Configure the Kaggle API credentials by following [Kaggle's API instructions](https://www.kaggle.com/docs/api).
3. From the repository root, download and extract the dataset:

   ```bash
   python -m pip install kaggle
   kaggle datasets download -d mashlyn/online-retail-ii-uci -p data/raw --unzip
   ```

The analysis reads Excel workbooks (including all sheets) or CSV files from `data/raw/`.

## Run the analysis

Python 3.10 or newer is recommended.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python src/analyze_retail.py
```

On Windows, activate the virtual environment with `.venv\Scripts\activate`.

You can provide a different input file/directory or output directory:

```bash
python src/analyze_retail.py --input path/to/online_retail_II.xlsx --output reports
```

Run the automated cleaning and report-generation checks with:

```bash
python -m unittest discover -s tests -v
```

## Cleaning and analysis approach

- Standardizes column names and whitespace, parses dates, and converts numeric fields.
- Removes exact duplicate rows.
- Retains transactions with missing customer IDs for sales totals, while excluding them from unique-customer counts.
- Labels missing product descriptions and countries as `Unknown product` and `Unknown country`.
- Excludes cancellations, returns/non-positive quantities, non-positive prices, missing invoice numbers, and invalid dates from gross sales analysis.
- Calculates line revenue as `Quantity × UnitPrice`. Revenue is reported in the dataset's currency units; the dataset does not provide a currency conversion.

The data-quality report makes the exclusions and retained missing values visible.

## Generated files

The `reports/` directory contains:

- `retail_sales_analysis.xlsx` — summary, data quality, monthly revenue, country performance, and top products sheets.
- CSV versions of the analysis tables and cleaned sales rows.
- `figures/monthly_revenue.png`, `figures/top_countries.png`, and `figures/top_products.png`.

Generated outputs and the raw dataset are excluded from Git by default. Remove the relevant `.gitignore` entries if you intentionally want to publish selected report outputs.

## Publish to GitHub

Create an empty repository on GitHub, then run these commands from this folder (replace the URL with your repository URL):

```bash
git init
git add .gitignore README.md requirements.txt src data reports
git commit -m "Add retail sales analysis project"
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repository>.git
git push -u origin main
```

Do not add Kaggle API credentials or the downloaded dataset to the repository.

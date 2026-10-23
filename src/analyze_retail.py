"""Clean and analyze the Kaggle Online Retail II dataset."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


REQUIRED_COLUMNS = {
    "invoice": "Invoice",
    "stockcode": "StockCode",
    "description": "Description",
    "quantity": "Quantity",
    "invoicedate": "InvoiceDate",
    "price": "UnitPrice",
    "customerid": "CustomerID",
    "country": "Country",
}


def normalize_column_name(column: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(column).lower())


def load_transactions(input_path: Path) -> pd.DataFrame:
    if input_path.is_file():
        files = [input_path]
    elif input_path.is_dir():
        files = sorted(
            path
            for path in input_path.iterdir()
            if path.is_file() and path.suffix.lower() in {".xlsx", ".xls", ".csv"}
        )
    else:
        files = []

    if not files:
        raise FileNotFoundError(
            f"No .xlsx, .xls, or .csv dataset files found at {input_path}"
        )

    frames: list[pd.DataFrame] = []
    for file_path in files:
        if file_path.suffix.lower() == ".csv":
            frames.append(pd.read_csv(file_path, low_memory=False))
        else:
            sheets = pd.read_excel(file_path, sheet_name=None)
            frames.extend(sheets.values())

    transactions = pd.concat(frames, ignore_index=True)
    normalized = {
        normalize_column_name(column): column for column in transactions.columns
    }
    if "price" not in normalized and "unitprice" in normalized:
        normalized["price"] = normalized["unitprice"]
    missing = set(REQUIRED_COLUMNS) - normalized.keys()
    if missing:
        expected = ", ".join(REQUIRED_COLUMNS.values())
        raise ValueError(
            f"Dataset is missing required columns {sorted(missing)}. "
            f"Expected columns equivalent to: {expected}"
        )

    transactions = transactions.rename(
        columns={
            normalized[key]: name
            for key, name in REQUIRED_COLUMNS.items()
        }
    )
    return transactions[list(REQUIRED_COLUMNS.values())].copy()


def clean_transactions(
    transactions: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw_rows = len(transactions)
    duplicate_rows = int(transactions.duplicated().sum())
    data = transactions.drop_duplicates().copy()

    data["Invoice"] = data["Invoice"].astype("string").str.strip()
    data["Invoice"] = data["Invoice"].replace("", pd.NA)
    data["StockCode"] = data["StockCode"].astype("string").str.strip()
    data["Description"] = data["Description"].astype("string").str.strip()
    data["Country"] = data["Country"].astype("string").str.strip()
    data["Quantity"] = pd.to_numeric(data["Quantity"], errors="coerce")
    data["UnitPrice"] = pd.to_numeric(data["UnitPrice"], errors="coerce")
    data["CustomerID"] = pd.to_numeric(data["CustomerID"], errors="coerce")
    data["InvoiceDate"] = pd.to_datetime(data["InvoiceDate"], errors="coerce")

    missing_customer_ids = int(data["CustomerID"].isna().sum())
    missing_descriptions = int(
        (data["Description"].isna() | data["Description"].eq("")).sum()
    )
    data["Description"] = data["Description"].replace("", pd.NA).fillna(
        "Unknown product"
    )
    data["Country"] = data["Country"].replace("", pd.NA).fillna("Unknown country")

    invalid_dates = int(data["InvoiceDate"].isna().sum())
    missing_invoices = int(data["Invoice"].isna().sum())
    cancellation_or_return = data["Invoice"].str.upper().str.startswith(
        "C", na=False
    ) | data["Quantity"].le(0)
    cancelled_or_return_rows = int(cancellation_or_return.sum())
    invalid_quantity_rows = int(data["Quantity"].isna().sum())
    invalid_price_rows = int((data["UnitPrice"].isna() | (data["UnitPrice"] <= 0)).sum())

    valid_sales = data.loc[
        data["Invoice"].notna()
        & data["InvoiceDate"].notna()
        & ~data["Invoice"].str.upper().str.startswith("C", na=False)
        & data["Quantity"].gt(0)
        & data["UnitPrice"].gt(0)
    ].copy()
    valid_sales["Revenue"] = valid_sales["Quantity"] * valid_sales["UnitPrice"]
    valid_sales["InvoiceDate"] = pd.to_datetime(valid_sales["InvoiceDate"])
    valid_sales["Month"] = valid_sales["InvoiceDate"].dt.to_period("M").astype(str)
    valid_sales["CustomerID"] = valid_sales["CustomerID"].astype("Int64")

    quality = pd.DataFrame(
        [
            ("Rows loaded", raw_rows),
            ("Exact duplicate rows removed", duplicate_rows),
            ("Rows after deduplication", len(data)),
            ("Rows with missing customer ID (retained)", missing_customer_ids),
            ("Rows with missing product description (labeled)", missing_descriptions),
            ("Rows with invalid/missing invoice date", invalid_dates),
            ("Rows with missing invoice number", missing_invoices),
            ("Cancellation/return rows excluded", cancelled_or_return_rows),
            ("Rows with invalid/missing quantity", invalid_quantity_rows),
            ("Rows with invalid/non-positive unit price", invalid_price_rows),
            ("Valid sales rows analyzed", len(valid_sales)),
        ],
        columns=["Data quality check", "Rows"],
    )
    return valid_sales, quality


def build_summary(sales: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("Total revenue", sales["Revenue"].sum()),
            ("Transactions", len(sales)),
            ("Unique invoices", sales["Invoice"].nunique()),
            ("Unique customers", sales["CustomerID"].nunique()),
            ("Units sold", sales["Quantity"].sum()),
            ("Countries served", sales["Country"].nunique()),
            ("Average order value", sales.groupby("Invoice")["Revenue"].sum().mean()),
            ("First transaction date", sales["InvoiceDate"].min()),
            ("Last transaction date", sales["InvoiceDate"].max()),
        ],
        columns=["Metric", "Value"],
    )


def build_reports(sales: pd.DataFrame) -> dict[str, pd.DataFrame]:
    monthly = (
        sales.groupby("Month", as_index=False)
        .agg(Revenue=("Revenue", "sum"), Orders=("Invoice", "nunique"))
        .sort_values("Month")
    )
    countries = (
        sales.groupby("Country", as_index=False)
        .agg(Revenue=("Revenue", "sum"), Orders=("Invoice", "nunique"))
        .sort_values("Revenue", ascending=False)
    )
    products = (
        sales.groupby(["StockCode", "Description"], as_index=False)
        .agg(
            Revenue=("Revenue", "sum"),
            UnitsSold=("Quantity", "sum"),
            Orders=("Invoice", "nunique"),
        )
        .sort_values("Revenue", ascending=False)
        .head(20)
    )
    return {
        "monthly_revenue": monthly,
        "revenue_by_country": countries,
        "top_products": products,
    }


def save_charts(reports: dict[str, pd.DataFrame], figures_dir: Path) -> None:
    figures_dir.mkdir(parents=True, exist_ok=True)

    monthly = reports["monthly_revenue"]
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(monthly["Month"], monthly["Revenue"], marker="o", linewidth=2)
    ax.set(title="Monthly Revenue", xlabel="Month", ylabel="Revenue")
    ax.tick_params(axis="x", rotation=60)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(figures_dir / "monthly_revenue.png", dpi=160)
    plt.close(fig)

    countries = reports["revenue_by_country"].head(10).sort_values("Revenue")
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.barh(countries["Country"], countries["Revenue"], color="#2878B5")
    ax.set(title="Top 10 Countries by Revenue", xlabel="Revenue", ylabel="Country")
    fig.tight_layout()
    fig.savefig(figures_dir / "top_countries.png", dpi=160)
    plt.close(fig)

    products = reports["top_products"].head(10).sort_values("Revenue")
    labels = products["Description"].str.slice(0, 35)
    fig, ax = plt.subplots(figsize=(10, 7))
    ax.barh(labels, products["Revenue"], color="#55A868")
    ax.set(title="Top 10 Products by Revenue", xlabel="Revenue", ylabel="Product")
    fig.tight_layout()
    fig.savefig(figures_dir / "top_products.png", dpi=160)
    plt.close(fig)


def analyze(input_path: Path, output_dir: Path) -> None:
    transactions = load_transactions(input_path)
    sales, quality = clean_transactions(transactions)
    if sales.empty:
        raise ValueError(
            "No valid sales rows remain after cleaning. Check the input data columns "
            "and values."
        )

    summary = build_summary(sales)
    reports = build_reports(sales)
    output_dir.mkdir(parents=True, exist_ok=True)
    figures_dir = output_dir / "figures"
    save_charts(reports, figures_dir)

    workbook_path = output_dir / "retail_sales_analysis.xlsx"
    with pd.ExcelWriter(workbook_path) as writer:
        summary.to_excel(writer, sheet_name="Summary", index=False)
        quality.to_excel(writer, sheet_name="Data Quality", index=False)
        for sheet_name, report in reports.items():
            report.to_excel(writer, sheet_name=sheet_name, index=False)

    for name, report in reports.items():
        report.to_csv(output_dir / f"{name}.csv", index=False)
    quality.to_csv(output_dir / "data_quality.csv", index=False)
    sales.to_csv(output_dir / "cleaned_sales.csv", index=False)

    print(f"Analysis complete: {workbook_path}")
    print(f"Charts saved in: {figures_dir}")
    print(summary.to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze Kaggle's Online Retail II sales dataset."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/raw"),
        help="Dataset file or directory containing Excel/CSV files (default: data/raw)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports"),
        help="Directory for Excel, CSV, and chart outputs (default: reports)",
    )
    args = parser.parse_args()
    analyze(args.input, args.output)


if __name__ == "__main__":
    main()

"""Clean and analyze the Kaggle Online Retail II dataset."""

from __future__ import annotations

import argparse
import re
import hashlib
import json
import numpy as np
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
    if "invoice" not in normalized and "invoiceno" in normalized:
        normalized["invoice"] = normalized["invoiceno"]
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
    data["CustomerID"] = data["CustomerID"].where(
        np.isfinite(data["CustomerID"]) & data["CustomerID"].mod(1).eq(0)
    )
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
        & np.isfinite(data["Quantity"])
        & np.isfinite(data["UnitPrice"])
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
            ("Rows with missing customer ID before sales filtering", missing_customer_ids),
            ("Rows with missing customer ID (retained)", int(valid_sales["CustomerID"].isna().sum())),
            ("Rows with missing product description (labeled)", missing_descriptions),
            ("Rows with invalid/missing invoice date", invalid_dates),
            ("Rows with missing invoice number", missing_invoices),
            ("Cancellation/return rows excluded", cancelled_or_return_rows),
            ("Rows with invalid/missing quantity", invalid_quantity_rows),
            ("Rows with invalid/non-positive unit price", invalid_price_rows),
            ("Rows excluded after deduplication (distinct)", len(data) - len(valid_sales)),
            ("Valid sales rows analyzed", len(valid_sales)),
        ],
        columns=["Data quality check", "Rows"],
    )
    return valid_sales, quality


def build_summary(sales: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("Gross sales (GBP)", sales["Revenue"].sum()),
            ("Sales line items", len(sales)),
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


# Explicitly reviewed non-merchandise codes; do not reject all alphabetic codes.
NON_MERCHANDISE_CODES = {
    "ADJUST", "ADJUST2", "AMAZONFEE", "B", "BANK CHARGES", "C2", "D",
    "DOT", "M", "POST", "S", "TEST001", "TEST002",
}


def classify_stock_codes(sales: pd.DataFrame) -> pd.Series:
    codes = sales["StockCode"].astype("string").str.upper()
    excluded = codes.isin(NON_MERCHANDISE_CODES) | codes.str.startswith("GIFT_", na=False)
    return pd.Series(np.where(excluded, "Other charges / non-merchandise", "Merchandise"),
                     index=sales.index)


def build_yoy(monthly: pd.DataFrame) -> pd.DataFrame:
    """Match full observed months to the same calendar month one year earlier."""
    complete = monthly.loc[monthly["Coverage"].eq("Full month within observed window")].copy()
    prior = complete[["Month", "Revenue", "Orders"]].copy()
    prior["Month"] = (pd.PeriodIndex(prior["Month"], freq="M") + 12).astype(str)
    prior = prior.rename(columns={"Revenue": "PriorYearRevenue", "Orders": "PriorYearOrders"})
    result = complete[["Month", "Revenue", "Orders"]].merge(prior, on="Month", how="inner")
    result["RevenueChange"] = result["Revenue"] - result["PriorYearRevenue"]
    result["RevenueGrowth"] = result["Revenue"] / result["PriorYearRevenue"].replace(0, np.nan) - 1
    return result.sort_values("Month")


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
    classified = sales.assign(SalesType=classify_stock_codes(sales))
    sales_mix = classified.groupby("SalesType", as_index=False).agg(Revenue=("Revenue", "sum"), Lines=("Revenue", "size"))
    merchandise = classified.loc[classified["SalesType"].eq("Merchandise")]
    products = (
        merchandise.groupby("StockCode", as_index=False)
        .agg(
            Description=("Description", "first"),
            Revenue=("Revenue", "sum"),
            UnitsSold=("Quantity", "sum"),
            Orders=("Invoice", "nunique"),
        )
        .sort_values("Revenue", ascending=False)
        .head(20)
    )
    # A customer can appear in multiple countries; count distinct invoices per ID.
    customers = sales.dropna(subset=["CustomerID"]).groupby("CustomerID").agg(
        Orders=("Invoice", "nunique"), Revenue=("Revenue", "sum")
    )
    customers["PurchasePattern"] = np.where(customers["Orders"].gt(1), "Repeat buyer", "One-order buyer")
    patterns = customers.groupby("PurchasePattern", as_index=False).agg(
        Customers=("Orders", "size"), Orders=("Orders", "sum"), Revenue=("Revenue", "sum")
    )
    patterns["CustomerShare"] = patterns["Customers"] / max(len(customers), 1)
    monthly["Coverage"] = "Full month within observed window"
    first, last = sales["InvoiceDate"].min(), sales["InvoiceDate"].max()
    if first.day != 1:
        monthly.loc[monthly["Month"].eq(str(first.to_period("M"))), "Coverage"] = "Partial month"
    if last.day != last.days_in_month:
        monthly.loc[monthly["Month"].eq(str(last.to_period("M"))), "Coverage"] = "Partial month"
    return {
        "year_over_year": build_yoy(monthly),
        "sales_mix": sales_mix,
        "customer_patterns": patterns,
        "monthly_revenue": monthly,
        "revenue_by_country": countries,
        "top_products": products,
    }


def save_charts(reports: dict[str, pd.DataFrame], figures_dir: Path) -> None:
    figures_dir.mkdir(parents=True, exist_ok=True)

    plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False,
                         "font.size": 11, "axes.titleweight": "bold"})
    monthly = reports["monthly_revenue"]
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(monthly["Month"], monthly["Revenue"], marker="o", linewidth=2)
    ax.set(title="Monthly gross sales", xlabel="Month", ylabel="Gross sales (GBP)")
    ticks = sorted(set(range(0, len(monthly), 4)) | {len(monthly) - 1})
    ax.set_xticks(ticks, monthly["Month"].iloc[ticks])
    ax.set_ylim(bottom=0)
    partial = monthly[monthly["Coverage"].eq("Partial month")]
    for idx, row in partial.iterrows():
        ax.annotate("Partial month", (idx, row["Revenue"]), xytext=(-70, 22),
                    textcoords="offset points", arrowprops={"arrowstyle": "->"})
    ax.yaxis.set_major_formatter(matplotlib.ticker.StrMethodFormatter("£{x:,.0f}"))
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(figures_dir / "monthly_revenue.png", dpi=160)
    plt.close(fig)

    countries = reports["revenue_by_country"].head(10).sort_values("Revenue")
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.barh(countries["Country"], countries["Revenue"], color="#2878B5")
    ax.set(title="Top 10 countries by gross sales", xlabel="Gross sales (GBP)", ylabel="Country")
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, pos: f"£{x / 1e6:,.1f}m"))
    fig.tight_layout()
    fig.savefig(figures_dir / "top_countries.png", dpi=160)
    plt.close(fig)

    products = reports["top_products"].head(10).sort_values("Revenue")
    labels = products["Description"].str.slice(0, 35)
    fig, ax = plt.subplots(figsize=(10, 7))
    ax.barh(labels, products["Revenue"], color="#55A868")
    ax.set(title="Top 10 merchandise products by gross sales", xlabel="Gross sales (GBP)", ylabel="Product")
    ax.xaxis.set_major_formatter(matplotlib.ticker.StrMethodFormatter("£{x:,.0f}"))
    fig.tight_layout()
    fig.savefig(figures_dir / "top_products.png", dpi=160)
    plt.close(fig)

    yoy = reports["year_over_year"]
    if not yoy.empty:
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.plot(yoy["Month"], yoy["PriorYearRevenue"], marker="o", linestyle="--", color="#697586", label="Same month, previous year")
        ax.plot(yoy["Month"], yoy["Revenue"], marker="o", color="#2878B5", label="Current year")
        ax.set(title="Year-over-year gross sales · matched complete months", ylabel="Gross sales (GBP)", xlabel="Comparison month", ylim=(0, None))
        ticks = sorted(set(range(0, len(yoy), 2)) | {len(yoy)-1})
        ax.set_xticks(ticks, yoy["Month"].iloc[ticks])
        ax.yaxis.set_major_formatter(matplotlib.ticker.StrMethodFormatter("£{x:,.0f}"))
        ax.grid(axis="y", alpha=.2)
        ax.legend(frameon=False)
        fig.tight_layout()
        fig.savefig(figures_dir / "year_over_year.png", dpi=160)
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

    summary.to_csv(output_dir / "summary.csv", index=False)
    source_files = [input_path] if input_path.is_file() else sorted(
        p for p in input_path.iterdir() if p.suffix.lower() in {".csv", ".xls", ".xlsx"})
    manifest = {"source": "https://www.kaggle.com/datasets/mashlyn/online-retail-ii-uci",
                "files": [{"name": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                          for p in source_files], "rows_loaded": len(transactions),
                "rows_analyzed": len(sales), "pandas_version": pd.__version__}
    (output_dir / "provenance.json").write_text(json.dumps(manifest, indent=2) + "\n")
    workbook_path = output_dir / "retail_sales_analysis.xlsx"
    with pd.ExcelWriter(workbook_path, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="Summary", index=False)
        quality.to_excel(writer, sheet_name="Data Quality", index=False)
        for sheet_name, report in reports.items():
            report.to_excel(writer, sheet_name=sheet_name, index=False)

    from openpyxl import load_workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.chart import LineChart, Reference
    from openpyxl.utils import get_column_letter
    book = load_workbook(workbook_path)
    notes = book.create_sheet("Methodology")
    for row in [
        ["Topic", "Definition / limitation"],
        ["Source", "Kaggle: mashlyn/online-retail-ii-uci; UCI DOI 10.24432/C5CG6D"],
        ["Grain", "Each record is an invoice line, not a whole order."],
        ["Gross sales", "Quantity × UnitPrice (GBP); positive sales only; not profit or net revenue."],
        ["Coverage", "2009-12-01 to 2011-12-09; December 2011 is incomplete."],
        ["Duplicates", "Exact source rows removed; some may be legitimate repeated lines."],
        ["Quality", "Issue counts overlap. Only distinct exclusions reconcile to row totals."],
        ["Customers", "Missing IDs retained for sales, excluded from customer patterns."],
        ["Repeat buyer", "Known customer with more than one distinct invoice in this window."],
        ["Products", "Ranked by StockCode; first observed description used as display label."],
        ["Scope", "Gross totals retain all valid sales; product rankings exclude reviewed charges, vouchers and test codes."],
        ["Year over year", "Same calendar month in consecutive years; only full months within the observed window."],
        ["Product exclusions", ", ".join(sorted(NON_MERCHANDISE_CODES)) + "; GIFT_* vouchers (case insensitive)"],
    ]:
        notes.append(row)
    for sheet in book:
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        sheet.sheet_view.showGridLines = False
        for cell in sheet[1]:
            cell.font = Font(color="FFFFFF", bold=True)
            cell.fill = PatternFill("solid", fgColor="17365D")
        sheet.row_dimensions[1].height = 26
        for col in sheet.columns:
            width = min(65, max(18, max(len(str(c.value or "")) for c in col) + 2))
            sheet.column_dimensions[get_column_letter(col[0].column)].width = width
        for row in sheet.iter_rows(min_row=2):
            for cell in row:
                if cell.row % 2 == 0:
                    cell.fill = PatternFill("solid", fgColor="EEF3F8")
                if isinstance(cell.value, (float, int)):
                    header = sheet.cell(1, cell.column).value
                    cell.number_format = '£#,##0.00' if header in {'Revenue', 'PriorYearRevenue', 'RevenueChange'} else ('0.0%' if header in {'CustomerShare', 'RevenueGrowth'} else '#,##0.##')
                if isinstance(cell.value, str):
                    cell.data_type = "s"  # Source text must never become an Excel formula.
    for row in notes.iter_rows(min_row=2):
        row[1].alignment = Alignment(wrap_text=True, vertical="top")
        notes.row_dimensions[row[0].row].height = 32
    chart = LineChart()
    chart.title = "Monthly gross sales (GBP) — final month partial"
    sheet = book["monthly_revenue"]
    chart.add_data(Reference(sheet, min_col=2, min_row=1, max_row=sheet.max_row), titles_from_data=True)
    chart.set_categories(Reference(sheet, min_col=1, min_row=2, max_row=sheet.max_row))
    chart.width, chart.height = 25, 12
    sheet.add_chart(chart, "G2")
    book.save(workbook_path)

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

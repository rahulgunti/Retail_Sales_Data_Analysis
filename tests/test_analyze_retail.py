import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.analyze_retail import analyze, clean_transactions


class AnalyzeRetailTests(unittest.TestCase):
    def setUp(self) -> None:
        self.transactions = pd.DataFrame(
            [
                ["10001", "A1", " Mug ", 2, "2010-12-01 08:00", 3.5, 1, " UK "],
                ["10001", "A1", " Mug ", 2, "2010-12-01 08:00", 3.5, 1, " UK "],
                ["10002", "B2", None, 1, "2010-12-02 09:00", 4.0, None, "France"],
                ["C10003", "C3", "Cancelled", -1, "2010-12-03 10:00", 2.0, 2, "UK"],
                ["10004", "D4", "Returned", -2, "2010-12-04 10:00", 2.0, 2, "UK"],
                ["10005", "E5", "Free item", 1, "2010-12-05 10:00", 0, 3, "UK"],
                ["10006", "F6", "Bad date", 1, "not a date", 1.0, 4, "UK"],
                [" ", "G7", "No invoice", 1, "2010-12-07 10:00", 1.0, 5, "UK"],
            ],
            columns=[
                "Invoice",
                "StockCode",
                "Description",
                "Quantity",
                "InvoiceDate",
                "UnitPrice",
                "CustomerID",
                "Country",
            ],
        )

    def test_cleaning_and_quality_counts(self) -> None:
        sales, quality = clean_transactions(self.transactions)
        checks = quality.set_index("Data quality check")["Rows"]

        self.assertEqual(len(sales), 2)
        self.assertEqual(sales["Revenue"].sum(), 11.0)
        self.assertEqual(sales["CustomerID"].nunique(), 1)
        self.assertEqual(sales["Country"].tolist(), ["UK", "France"])
        self.assertEqual(checks["Exact duplicate rows removed"], 1)
        self.assertEqual(checks["Rows with missing customer ID (retained)"], 1)
        self.assertEqual(checks["Rows with missing product description (labeled)"], 1)
        self.assertEqual(checks["Cancellation/return rows excluded"], 2)
        self.assertEqual(checks["Rows with invalid/missing invoice date"], 1)
        self.assertEqual(checks["Rows with missing invoice number"], 1)

    def test_analysis_writes_workbook_csvs_and_charts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_file = root / "transactions.csv"
            output_dir = root / "reports"
            self.transactions.to_csv(input_file, index=False)

            analyze(input_file, output_dir)

            self.assertTrue((output_dir / "retail_sales_analysis.xlsx").is_file())
            self.assertTrue((output_dir / "monthly_revenue.csv").is_file())
            self.assertTrue((output_dir / "cleaned_sales.csv").is_file())
            self.assertTrue((output_dir / "figures" / "monthly_revenue.png").is_file())
            self.assertTrue((output_dir / "figures" / "top_countries.png").is_file())
            self.assertTrue((output_dir / "figures" / "top_products.png").is_file())


if __name__ == "__main__":
    unittest.main()

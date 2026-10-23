import unittest
import pandas as pd
from src.analyze_retail import build_reports, clean_transactions


class ReportingTests(unittest.TestCase):
    def test_product_identity_customer_population_and_reconciliation(self):
        frame = pd.DataFrame([
            ['1', 'A', 'Old name', 2, '2011-12-01', 5, 7, 'UK'],
            ['2', 'A', 'New name', 1, '2011-12-09', 5, 7, 'UK'],
            ['3', 'B', 'Cup', 1, '2011-12-09', 3, None, 'France'],
            ['C4', 'A', 'Return', -1, '2011-12-09', 5, None, 'UK'],
        ], columns=['Invoice', 'StockCode', 'Description', 'Quantity',
                    'InvoiceDate', 'UnitPrice', 'CustomerID', 'Country'])
        sales, quality = clean_transactions(frame)
        reports = build_reports(sales)
        for key in ['monthly_revenue', 'revenue_by_country']:
            self.assertEqual(reports[key].Revenue.sum(), 18)
        self.assertEqual(reports['top_products'].iloc[0].Revenue, 15)
        self.assertEqual(reports['customer_patterns'].iloc[0].Customers, 1)
        self.assertEqual(reports['customer_patterns'].iloc[0].PurchasePattern, 'Repeat buyer')
        self.assertEqual(reports['monthly_revenue'].iloc[0].Coverage, 'Partial month')
        q = quality.set_index('Data quality check').Rows
        self.assertEqual(q['Rows with missing customer ID (retained)'], 1)
        self.assertEqual(q['Rows loaded'], q['Exact duplicate rows removed'] +
                         q['Rows excluded after deduplication (distinct)'] +
                         q['Valid sales rows analyzed'])

    def test_nonfinite_values_are_excluded(self):
        frame = pd.DataFrame([['1', 'A', 'Cup', float('inf'), '2011-12-01', 5, 7, 'UK']],
                             columns=['Invoice', 'StockCode', 'Description', 'Quantity',
                                      'InvoiceDate', 'UnitPrice', 'CustomerID', 'Country'])
        self.assertTrue(clean_transactions(frame)[0].empty)

    def test_yoy_matches_calendar_months_and_excludes_partial_months(self):
        from src.analyze_retail import build_yoy
        monthly = pd.DataFrame({
            'Month': ['2010-01', '2010-02', '2010-12', '2011-01', '2011-02', '2011-12'],
            'Revenue': [100, 0, 300, 120, 50, 90],
            'Orders': [10, 0, 30, 12, 5, 9],
            'Coverage': ['Full month within observed window'] * 5 + ['Partial month'],
        })
        result = build_yoy(monthly)
        self.assertEqual(result.Month.tolist(), ['2011-01', '2011-02'])
        self.assertAlmostEqual(result.iloc[0].RevenueGrowth, .2)
        self.assertTrue(pd.isna(result.iloc[1].RevenueGrowth))

    def test_merchandise_classification_preserves_alphabetic_products(self):
        from src.analyze_retail import classify_stock_codes
        frame = pd.DataFrame({'StockCode': ['22423', 'DCGS0003', 'm', 'POST', 'gift_0001_10', 'TEST001']})
        result = classify_stock_codes(frame)
        self.assertEqual(result.eq('Merchandise').tolist(), [True, True, False, False, False, False])

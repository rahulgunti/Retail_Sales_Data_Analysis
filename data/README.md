# Source data

Place the extracted Kaggle CSV or UCI workbook in `raw/`. Use **one copy** of the dataset, not both CSV and Excel copies. All workbook sheets are read.

- Requested source: https://www.kaggle.com/datasets/mashlyn/online-retail-ii-uci
- Original publisher: https://archive.ics.uci.edu/dataset/502/online+retail+ii
- Citation: Chen, D. (2012). Online Retail II [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C5CG6D
- Original dataset license: CC BY 4.0. Verify terms on the download page.
- Observed local CSV: 1,067,371 invoice lines, December 1, 2009–December 9, 2011.
- Currency: pounds sterling (GBP). Country is customer country, not a region.

`reports/provenance.json` records input filenames, SHA-256 checksums, row counts, and the Pandas version. Raw data and customer-level cleaned data stay out of Git; committed reports contain aggregate results.

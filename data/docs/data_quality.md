# Data Quality Reference

## Source completeness
An analysis is only as complete as the source files loaded into the database. Check the ingestion report's row count and missing-value percentages before relying on an aggregate.

## Required sales fields
Sales analysis commonly requires order_date, region, quantity, unit_price, discount and revenue. If an uploaded source omits a field, questions requiring it cannot be answered from that source.

## Unique order identifiers
order_id identifies an order line in the sales example. A source may contain several lines for one order, so counting rows is not necessarily the same as counting distinct orders.

## Date representation
Date-like column names are parsed during cleaning when at least 80 percent of their values are parseable. ISO year-month-day strings can be grouped consistently across SQLite and PostgreSQL.

## Valid discount values
The example policy caps a normal discount at 25 percent. Values outside the expected interval should be investigated rather than silently corrected during analysis.

## Revenue reconciliation
For each sales line, compare stored revenue with quantity multiplied by unit_price multiplied by one minus discount. Differences may indicate a source calculation or rounding issue.

## Return matching
Returns can be matched to sales using order_id. A return file with identifiers absent from sales should be checked before computing net sales or refund rates.

## Target coverage
The example target data has one value for each region and quarter. Missing region-quarter combinations mean target comparisons are incomplete.

## Missing categories
Null categories are excluded from grouped summaries that use a category column. Review null percentages before interpreting the group totals as exhaustive.

## Duplicate records
Ingestion removes fully duplicated rows and reports the number removed. The validation profile also reports repeated values per column; repeated values alone do not prove a record is duplicated.

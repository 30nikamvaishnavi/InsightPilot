# Analysis Playbook

## Gross revenue
Gross revenue is the sum of the stored revenue column. It does not subtract refunds, taxes or shipping unless those amounts are separately modeled and explicitly included in the calculation.

## Net sales
Net sales after returns can be calculated by subtracting refund_amount from gross revenue after matching return records to the corresponding sales rows. Avoid subtracting the same refund more than once.

## Units sold
Units sold is the sum of quantity for the selected time period, category or region. A count of sales rows answers a different question from the number of units.

## Average order value
Average order value is revenue divided by the number of orders for the same population and period. When the source is at order-line granularity, distinct order identifiers are needed for the denominator.

## Period growth
Percentage growth compares a current-period metric with its prior-period value: subtract the prior value and divide by that prior value. Growth is undefined when the prior value is zero.

## Group comparisons
Grouping by region or product gives a comparison only for rows that are present in the selected table. Check missing groups and filters before treating the output as a complete ranking.

## Top and bottom rows
A top-N or bottom-N query orders the selected measure and limits returned rows. The reported ranking is only as meaningful as the chosen measure and the data coverage.

## Correlation
Pearson correlation describes a linear association between two numeric columns. It does not establish that one variable caused a change in the other.

## Trend interpretation
A trend reports observed values by calendar period. Empty periods may be absent from the source, so adjacent returned periods are not always consecutive calendar periods.

## Uncertainty and clarification
When a question does not identify a supported metric or grouping, InsightPilot should ask for clarification or report that it cannot match the request rather than inventing a measure.

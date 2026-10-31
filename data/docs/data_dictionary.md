# Data Dictionary

## Sales table columns
The sales table has one row per order line. Columns: order_id (unique order identifier), order_date (date the order was placed, ISO format), region (North, South, East or West), category (product category), product (product name), quantity (units sold in the order line), unit_price (price of one unit before discount), discount (fraction between 0 and 1 taken off the price) and revenue (the calculated order value).

## Returns table columns
The returns table has one row per returned order. Columns: order_id (links back to the sales table), return_date (date the item came back), reason (why the customer returned it) and refund_amount (money paid back to the customer).

## Targets table columns
The targets table stores planned sales goals. Columns: region, quarter (Q1 to Q4) and target (the planned revenue for that region and quarter).

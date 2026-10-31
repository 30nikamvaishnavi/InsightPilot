# Support Workflows

## Return eligibility
Customers normally have 30 days from the order date to return an item. The policy exception for a damaged arrival should be checked against the case details.

## Damaged item refunds
Damaged products receive a full refund of the order value under the example policy. The return reason should be recorded as Damaged for reporting.

## Wrong item refunds
Wrong items receive a full refund of the order value under the example policy. Verify that the returned order is linked to its original sales record.

## Changed mind refunds
Changed-mind returns receive 90 percent of the order value after the restocking fee. The sample data records the resulting refund amount, not the fee as a separate field.

## Return authorization details
The example records an order identifier, return date, reason and refund amount. It does not contain a separate authorization status or approval timestamp.

## Order date and return date
The return window is measured from the order date, while the return record stores the date the item came back. These dates answer different operational questions.

## Discount approval
Discounts above 15 percent need written approval from the regional manager before confirmation. The approval evidence is not represented as a column in the sample sales table.

## Temporary promotions
The head of sales may temporarily raise the discount limit for a named campaign. Dates and limits are announced by email and are not present in the example data.

## Regional ownership
Each regional manager owns the quarterly target and reviews the monthly sales report. Regional managers report to the head of sales.

## Escalating data questions
When a return, discount or target question depends on a fact missing from the loaded data, use the policy documents and identify the missing field instead of inferring an operational outcome.

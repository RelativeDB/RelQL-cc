# RelQL query cookbook

Adapt these to the user's schema. Replace table/column names; keep the temporal
directions (target `FOLLOWING`, filter `PRECEDING`).

## Churn / lapse (binary classification)

```sql
-- Zero transactions in the next 30 days, among recently-active customers
PREDICT NOT EXISTS(transactions.*) OVER (30 DAYS FOLLOWING)
FOR EACH customers.customer_id
WHERE EXISTS(transactions.*) OVER (90 DAYS PRECEDING)
```

```sql
-- Same, with a calibrated probability output
PREDICT NOT EXISTS(transactions.*) OVER (30 DAYS FOLLOWING)
FOR EACH customers.customer_id
WHERE EXISTS(transactions.*) OVER (90 DAYS PRECEDING)
RETURN PROBABILITY
```

## Conversion / activation (binary classification)

```sql
-- Will a trial account create a paid subscription in the next 30 days?
PREDICT EXISTS(subscriptions.* WHERE subscriptions.plan != 'trial') OVER (30 DAYS FOLLOWING)
FOR EACH accounts.account_id
WHERE accounts.status = 'trial'
```

## Spend / LTV / demand (regression)

```sql
-- Total spend per customer over the next 30 days
PREDICT SUM(transactions.price) OVER (30 DAYS FOLLOWING)
FOR EACH customers.customer_id
```

```sql
-- Will spend in a future 15-45 day window exceed $100 (binary via comparison)
PREDICT SUM(transactions.value) OVER (RANGE BETWEEN 15 DAYS FOLLOWING AND 45 DAYS FOLLOWING) > 100
FOR EACH customers.customer_id
WHERE customers.location NOT IN ('ALASKA', 'HAWAII')
```

## Forecasting (value per horizon)

```sql
-- Daily usage for each account, next 4 weeks (28 one-day steps)
PREDICT SUM(usage.count) OVER (1 DAY FOLLOWING HORIZONS 28)
FOR EACH accounts.account_id
```

```sql
-- Weekly demand, 6 overlapping 30-day windows stepped by a week
PREDICT SUM(sales.qty) OVER (30 DAYS FOLLOWING HORIZONS 6 STEP 7 DAYS)
FOR EACH products.product_id
```

## Recommendation / ranking (parses; not executable on current checkpoint)

```sql
-- Top 12 articles a customer will buy next 30 days
PREDICT LIST_DISTINCT(transactions.article_id) OVER (30 DAYS FOLLOWING) RANK TOP 12
FOR EACH customers.customer_id
```

## Risk / status (binary classification)

```sql
-- Will the latest loan status NOT end in DENIED over the next 30 days?
PREDICT LAST(loan.status) OVER (30 DAYS FOLLOWING) NOT LIKE '%DENIED'
FOR EACH loan.id
```

## Missing-attribute prediction (static target)

```sql
PREDICT articles.description IS NULL
FOR EACH articles.id
```

## Scoped populations

```sql
-- Only specific entities, by primary key
PREDICT NOT EXISTS(orders.*) OVER (90 DAYS FOLLOWING)
FOR EACH users.user_id
WHERE users.user_id IN (42, 123)
```

```sql
-- Counterfactual assumption (parses/validates; not yet applied to context)
PREDICT NOT EXISTS(orders.*) OVER (90 DAYS FOLLOWING)
FOR EACH users.user_id
WHERE users.user_id = 42
ASSUMING users.plan = 'premium'
```

## Named window (reuse one frame)

```sql
-- Predicted gross margin over a single shared future window
PREDICT SUM(orders.revenue) OVER w - SUM(orders.cost) OVER w
FOR EACH customers.customer_id
WINDOW w AS (30 DAYS FOLLOWING)
```

## Filtered aggregate target

```sql
-- Total quantity, counting only orders with qty > 1
PREDICT SUM(orders.qty WHERE orders.qty > 1) OVER (30 DAYS FOLLOWING)
FOR EACH customers.customer_id
```

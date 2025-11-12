# 🚀 Quick Reference: SQLite Data Source in Grafana

A compact guide for building **robust, error-free dashboards** using **SQLite** as a data source in Grafana.

---

## ⚙️ 1. Plugin & Setup
- Use plugin: **frser-sqlite-datasource**
- Run Grafana with custom plugin directory (for non-sudo installs):
  ```bash
  GRAFANA_PLUGINS_DIR=../data/plugins ./grafana server web
  ```
- Data source config:
  - **Path:** absolute path to `.db` file  
  - **Access:** Server (default)  
  - ✅ Always test the connection before saving

---

## 🧩 2. Grafana Variables
| Variable | Type | Example Definition | Notes |
|-----------|------|--------------------|--------|
| `subreddit` | Query | `SELECT DISTINCT name FROM subreddits ORDER BY name;` | Enable *Multi-value* and *Include All*, set “Custom All Value” = `All` |
| `metric` | Custom | `num_posts_in_window, num_comments_in_window, average_upvotes_in_window, top_post_score_in_window` | Column selector |
| `aggregation_window` | Custom | `10,30,60` | Numeric values in minutes |

---

## 🧠 3. Query Building Rules (SQLite specifics)
1. **Do not use** Grafana macros like `$__timeFilter()`.  
   Instead use:
   ```sql
   STRFTIME('%s', a.timestamp)
     BETWEEN CAST($__from / 1000 AS INTEGER)
         AND CAST($__to / 1000 AS INTEGER)
   ```
2. **Handle multi-select variables properly:**
   - ❌ `IN (${subreddit:csv})`
   - ✅ `IN (${subreddit:singlequote})`
3. **Always cast numeric variables before math:**
   ```sql
   CAST($aggregation_window AS INTEGER)
   ```
4. **Avoid unsupported macros like `$__join()` or `$__interval_ms`**.

---

## 🕒 4. Time Bucketing
SQLite lacks `date_trunc()`. Use integer flooring for custom time buckets:
```sql
CAST(STRFTIME('%s', a.timestamp) / (CAST($aggregation_window AS INTEGER) * 60) AS INTEGER)
    * (CAST($aggregation_window AS INTEGER) * 60) AS time
```
- This produces **window start times** (Grafana X-axis).  
- To mark the **window end**, add `+ ($aggregation_window * 60)`.

---

## 🧱 5. Expected Output Format
Grafana expects **long format** data:

| Column | Role |
|---------|------|
| `time` | Epoch seconds or ISO timestamp (X-axis) |
| `metric` | Series name (e.g., subreddit) |
| `value` | Numeric value (Y-axis) |

Example structure:
```sql
time | metric | value
```

---

## ⚠️ 6. Common Pitfalls & Fixes
| Issue | Cause | Fix |
|--------|--------|-----|
| **Unrecognized token `{`** | Grafana variable expansion syntax | Use `${var:singlequote}` |
| **Missing named argument** | Unsupported macro like `$__timeFilter()` | Use manual time filter with `$__from` / `$__to` |
| **NULL time values** | Bad or null timestamps | Add `WHERE a.timestamp IS NOT NULL` |
| **Cannot convert to wide series** | Returned table not long-format | Return only `time, metric, value` |
| **Unexpected time alignment** | Window midpoint confusion | Current bucketing gives window **start** (preferred) |

---

## 🎯 7. Best Practices
- Use **epoch seconds** (`STRFTIME('%s', ...)`) for time columns.
- Keep output as **3 columns**: `time`, `metric`, `value`.
- Wrap string variables in quotes; cast numeric variables explicitly.
- Check actual SQL using **Query Inspector** to debug expansions.
- Keep one flexible query per panel; use `$metric` and `$subreddit` selectors instead of hardcoding.
- Always ensure consistent time filtering via `$__from` / `$__to`.

---

### ✅ TL;DR
> Quote string vars, cast numeric vars, avoid Grafana macros, and keep data long-form (`time`, `metric`, `value`).  
> Manually handle time filters and bucketing in SQLite.  
> Inspect expanded queries when in doubt.  
> Result: SQLite dashboards behave like Postgres dashboards — without the hidden pitfalls.
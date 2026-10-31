"""Rule-based, schema-aware planner: question -> safe SELECT statement.

Identifiers only ever come from the real database schema, and filter values only
come from values that exist in the data, so generated SQL cannot be injected.
Swap in an LLM text-to-SQL planner by implementing ``plan()``; its SQL must still
pass ``tools.sql_guard.validate_sql``.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from ..ingestion.store import distinct_values, get_schema

NUMERIC_TYPES = {"INTEGER", "INT", "BIGINT", "SMALLINT", "REAL", "NUMERIC", "DECIMAL", "FLOAT", "DOUBLE", "DOUBLE PRECISION"}
TEXT_TYPES = {"TEXT", "CHARACTER VARYING", "CHARACTER", "VARCHAR", "CHAR", "STRING"}
SYNONYMS = {"sales": "revenue", "income": "revenue", "turnover": "revenue", "units": "quantity", "qty": "quantity", "volume": "quantity"}
TIME_WORDS = {"month": "month", "months": "month", "monthly": "month", "quarter": "quarter", "quarters": "quarter",
              "quarterly": "quarter", "year": "year", "years": "year", "yearly": "year"}
MONTHS = {m: f"{i:02d}" for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"], 1)}
AGG_NAMES = {"sum": "Total", "avg": "Average", "max": "Maximum", "min": "Minimum", "count": "Count"}
SQL_FUNCS = {"sum": "SUM", "avg": "AVG", "max": "MAX", "min": "MIN"}

GROWTH = re.compile(r"\b(trend|trends|growth|growing|month over month|mom|over time)\b")
CORRELATION = re.compile(r"\b(correlat\w*|relationship between|related to)\b")
DOC_INTENT = re.compile(
    r"\b(what does|what is|what are|what's|define|definition|meaning|explain|policy|policies|how is|how are|how do|how does|who|when does|when is|when are|which (?:states|months|column|columns|field|fields)|have to|allowed|must|need to|needs to|rules?|approve|approval|limits?)\b"
)


def _is_id(name: str) -> bool:
    return name == "id" or name.endswith("_id")


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _lit(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _norm(word: str) -> str:
    word = word.lower()
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        return word[:-1]
    return word


def match_column(word: str, columns: list[str]) -> str | None:
    if len(word) < 3:
        return None
    synonym = SYNONYMS.get(word.lower())
    if synonym and synonym in columns:
        return synonym
    target = _norm(word)
    for column in columns:
        if _norm(column) == target:
            return column
    for column in columns:
        if target in {_norm(token) for token in column.split("_")}:
            return column
    return None


@dataclass
class TableInfo:
    name: str
    columns: dict
    numeric: list
    categorical: dict
    date_col: str | None


class SchemaContext:
    def __init__(self, tables: dict[str, TableInfo]) -> None:
        self.tables = tables

    @classmethod
    def from_db(cls, db_path, max_categories: int = 50) -> "SchemaContext":
        tables: dict[str, TableInfo] = {}
        for name, cols in get_schema(db_path).items():
            kinds = {c["name"]: c["type"].upper() for c in cols}
            numeric = [c for c, t in kinds.items() if t in NUMERIC_TYPES and not _is_id(c)]
            date_kinds = TEXT_TYPES | {"DATE", "TIMESTAMP WITHOUT TIME ZONE", "TIMESTAMP WITH TIME ZONE"}
            date_col = next((c for c, t in kinds.items() if t in date_kinds and ("date" in c or c.endswith("_at"))), None)
            categorical = {}
            for column, kind in kinds.items():
                if kind in TEXT_TYPES and column != date_col and not _is_id(column):
                    values = distinct_values(db_path, name, column, limit=max_categories + 1)
                    if 0 < len(values) <= max_categories:
                        categorical[column] = values
            tables[name] = TableInfo(name, kinds, numeric, categorical, date_col)
        return cls(tables)

    def summary(self) -> dict:
        return {name: list(info.columns) for name, info in self.tables.items()}


@dataclass
class Plan:
    route: str
    table: str | None = None
    sql: str | None = None
    label: str = ""
    kind: str = ""  # scalar | grouped | rows | trend | correlation
    agg: str | None = None
    measure: str | None = None
    group: str | None = None
    columns: list = field(default_factory=list)
    limit: int | None = None
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class RulePlanner:
    def __init__(self, dialect: str = "sqlite") -> None:
        self.dialect = dialect

    def plan(self, question: str, ctx: SchemaContext, default_limit: int = 50) -> Plan:
        q = question.lower().strip()
        words = re.findall(r"[a-z0-9_]+", q)
        if not ctx.tables:
            return Plan(route="unknown", note="No data is loaded yet. Ingest a CSV, JSON or Excel file first.")

        table = self._choose_table(words, ctx)
        info = ctx.tables[table]
        agg = self._agg(q, words)
        measure = self._measure(words, info)
        group = self._group(q, words, info)
        filters, filter_texts = self._filters(q, info, self.dialect)
        topn = re.search(r"\b(top|bottom)\s+(\d+)\b", q)

        if CORRELATION.search(q):
            cols = []
            for word in words:
                col = match_column(word, info.numeric)
                if col and col not in cols:
                    cols.append(col)
            if len(cols) < 2:
                return self._ask_which(info, "Name two numeric columns to correlate.")
            return self._correlation_plan(info, cols[:2], filters, filter_texts)

        if GROWTH.search(q):
            if not info.date_col:
                return Plan(route="unknown", table=table, note=f"Table {table} has no date column, so I can't compute a trend.")
            if agg != "count" and not measure:
                return self._ask_which(info, "Which numeric column should I track over time?")
            return self._trend_plan(info, agg, measure, filters, filter_texts, self.dialect)

        if agg in ("sum", "avg", "max", "min") and group is not None and not measure:
            return self._ask_which(info, "Which numeric column should I aggregate?")

        has_filters = bool(filters)
        data_intent = bool(measure) and (agg is not None or group is not None or has_filters)
        if DOC_INTENT.search(q) and not data_intent:
            return Plan(route="docs", table=table)
        if data_intent or (agg == "count" and not DOC_INTENT.search(q)):
            return self._sql_plan(info, q, agg, measure, group, filters, filter_texts, topn, default_limit, self.dialect)
        if measure and agg is None:
            return Plan(route="docs", table=table)
        return Plan(route="docs", table=table)

    # ------------------------------------------------------------------ helpers
    def _choose_table(self, words: list[str], ctx: SchemaContext) -> str:
        scores = {}
        for name, info in ctx.tables.items():
            table_stems = {_norm(tok) for tok in name.split("_")}
            score = 0
            for word in words:
                if _norm(word) in table_stems:
                    score += 3
                if match_column(word, list(info.columns)):
                    score += 2
                if any(word == v.lower() for vals in info.categorical.values() for v in vals):
                    score += 1
            scores[name] = score
        return max(scores, key=lambda n: (scores[n], len(ctx.tables[n].columns)))

    @staticmethod
    def _agg(q: str, words: list[str]) -> str | None:
        word_set = set(words)
        if re.search(r"\bhow many\b|\bnumber of\b|\bcount\b", q):
            return "count"
        if word_set & {"average", "avg"}:
            return "avg"
        if word_set & {"total", "sum", "overall", "combined"}:
            return "sum"
        if word_set & {"highest", "maximum", "max", "largest", "biggest", "best", "top"}:
            return "max"
        if word_set & {"lowest", "minimum", "min", "smallest", "worst", "bottom"}:
            return "min"
        return None

    @staticmethod
    def _measure(words: list[str], info: TableInfo) -> str | None:
        for word in words:
            col = match_column(word, info.numeric)
            if col:
                return col
        return None

    @staticmethod
    def _group(q: str, words: list[str], info: TableInfo):
        candidates: list[str] = []
        for pattern in (
            r"\b(?:by|per|each|across)\s+(?:the\s+)?([a-z_]+)",
            r"\bwhich\s+([a-z_]+)",
            r"\b(?:top|bottom)\s+(?:\d+\s+)?([a-z_]+)",
        ):
            candidates += re.findall(pattern, q)
        for word in candidates:
            if word in TIME_WORDS:
                return ("time", TIME_WORDS[word])
            col = match_column(word, list(info.categorical))
            if col:
                return ("col", col)
        for word in words:
            if word in ("monthly", "quarterly", "yearly"):
                return ("time", TIME_WORDS[word])
        return None

    @staticmethod
    def _filters(q: str, info: TableInfo, dialect: str = "sqlite"):
        clauses, texts = [], []
        for column, values in info.categorical.items():
            for value in values:
                if re.search(rf"\b{re.escape(value.lower())}\b", q):
                    clauses.append(f"{_quote(column)} = {_lit(value)}")
                    texts.append(f"{column} = {value}")
                    break
        if info.date_col:
            date = _quote(info.date_col)
            year = re.search(r"\b(20\d\d)\b", q)
            if year:
                expression = f"EXTRACT(YEAR FROM {date}::date)::integer" if dialect == "postgresql" else f"strftime('%Y', {date})"
                clauses.append(f"{expression} = {year.group(1) if dialect == 'postgresql' else _lit(year.group(1))}")
                texts.append(f"year = {year.group(1)}")
            month = re.search(r"\bin\s+(" + "|".join(MONTHS) + r")\b", q)
            if month:
                expression = f"EXTRACT(MONTH FROM {date}::date)::integer" if dialect == "postgresql" else f"strftime('%m', {date})"
                value = str(int(MONTHS[month.group(1)])) if dialect == "postgresql" else _lit(MONTHS[month.group(1)])
                clauses.append(f"{expression} = {value}")
                texts.append(f"month = {month.group(1).title()}")
            quarter = re.search(r"\bq([1-4])\b", q)
            if quarter:
                expression = (f"EXTRACT(QUARTER FROM {date}::date)::integer" if dialect == "postgresql"
                              else f"((CAST(strftime('%m', {date}) AS INTEGER) + 2) / 3)")
                clauses.append(f"{expression} = {int(quarter.group(1))}")
                texts.append(f"quarter = Q{quarter.group(1)}")
        return clauses, texts

    @staticmethod
    def _where(filters: list[str]) -> str:
        return (" WHERE " + " AND ".join(filters)) if filters else ""

    @staticmethod
    def _time_expr(info: TableInfo, bucket: str, dialect: str = "sqlite") -> str:
        date = _quote(info.date_col)
        if dialect == "postgresql":
            cast_date = f"{date}::date"
            if bucket == "month":
                return f"to_char(date_trunc('month', {cast_date}), 'YYYY-MM')"
            if bucket == "quarter":
                return f"to_char(date_trunc('quarter', {cast_date}), 'YYYY') || '-Q' || EXTRACT(QUARTER FROM {cast_date})::integer"
            return f"to_char(date_trunc('year', {cast_date}), 'YYYY')"
        if bucket == "month":
            return f"strftime('%Y-%m', {date})"
        if bucket == "quarter":
            return f"strftime('%Y', {date}) || '-Q' || ((CAST(strftime('%m', {date}) AS INTEGER) + 2) / 3)"
        return f"strftime('%Y', {date})"

    @staticmethod
    def _suffix(texts: list[str]) -> str:
        return f" ({'; '.join(texts)})" if texts else ""

    def _ask_which(self, info: TableInfo, message: str) -> Plan:
        options = ", ".join(info.numeric) or "none"
        return Plan(route="unknown", table=info.name, note=f"{message} Numeric columns in {info.name}: {options}.")

    def _correlation_plan(self, info, cols, filters, texts) -> Plan:
        a, b = (_quote(c) for c in cols)
        extra = filters + [f"{a} IS NOT NULL", f"{b} IS NOT NULL"]
        sql = (f"SELECT COUNT(*) AS n, SUM({a}) AS sx, SUM({b}) AS sy, SUM({a} * {b}) AS sxy, "
               f"SUM({a} * {a}) AS sxx, SUM({b} * {b}) AS syy FROM {_quote(info.name)}{self._where(extra)}")
        label = f"Correlation between {cols[0]} and {cols[1]}{self._suffix(texts)}"
        return Plan(route="correlation", table=info.name, sql=sql, label=label, kind="correlation", columns=cols)

    def _trend_plan(self, info, agg, measure, filters, texts, dialect="sqlite") -> Plan:
        expr = self._time_expr(info, "month", dialect)
        if agg == "count":
            metric, alias, name = "COUNT(*)", "count", "Count of records"
        else:
            fn = SQL_FUNCS.get(agg or "sum", "SUM") if agg in ("avg",) else "SUM"
            metric, alias = f"{fn}({_quote(measure)})", f"{'avg' if fn == 'AVG' else 'total'}_{measure}"
            name = f"{'Average' if fn == 'AVG' else 'Total'} {measure.replace('_', ' ')}"
        sql = (f"SELECT {expr} AS \"month\", {metric} AS {_quote(alias)} FROM {_quote(info.name)}"
               f"{self._where(filters)} GROUP BY 1 ORDER BY 1")
        return Plan(route="trend", table=info.name, sql=sql, label=f"{name} by month{self._suffix(texts)}",
                    kind="trend", agg=agg, measure=measure, group="month")

    def _sql_plan(self, info, q, agg, measure, group, filters, texts, topn, default_limit, dialect="sqlite") -> Plan:
        table = _quote(info.name)
        where = self._where(filters)
        suffix = self._suffix(texts)

        if group is not None:
            kind, key = group
            if kind == "time" and not info.date_col:
                return Plan(route="unknown", table=info.name, note=f"Table {info.name} has no date column to group by {key}.")
            gexpr = self._time_expr(info, key, dialect) if kind == "time" else _quote(key)
            galias = key
            if agg == "count":
                metric, alias, name = "COUNT(*)", "count", "Count of records"
            else:
                if not measure:
                    return self._ask_which(info, "Which numeric column should I aggregate?")
                fn = "AVG" if agg == "avg" else "SUM"
                metric = f"{fn}({_quote(measure)})"
                alias = f"{'avg' if fn == 'AVG' else 'total'}_{measure}"
                name = f"{'Average' if fn == 'AVG' else 'Total'} {measure.replace('_', ' ')}"
            descending = not (agg == "min" or (topn and topn.group(1) == "bottom"))
            if kind == "time":
                order = "ORDER BY 1 ASC"
            else:
                order = f"ORDER BY 2 {'DESC' if descending else 'ASC'}, 1 ASC"
            if topn:
                limit = int(topn.group(2))
            elif agg in ("max", "min"):
                limit = 1
            else:
                limit = default_limit
            sql = (f"SELECT {gexpr} AS {_quote(galias)}, {metric} AS {_quote(alias)} FROM {table}{where} "
                   f"GROUP BY 1 {order} LIMIT {limit}")
            return Plan(route="sql", table=info.name, sql=sql, label=f"{name} by {galias}{suffix}", kind="grouped",
                        agg=agg or "sum", measure=measure, group=galias, limit=limit)

        if topn and measure:
            limit = int(topn.group(2))
            id_col = next((c for c in info.columns if _is_id(c)), None)
            columns = ([_quote(id_col)] if id_col else []) + [_quote(measure)]
            direction = "ASC" if topn.group(1) == "bottom" else "DESC"
            sql = f"SELECT {', '.join(columns)} FROM {table}{where} ORDER BY {_quote(measure)} {direction} LIMIT {limit}"
            word = "Bottom" if topn.group(1) == "bottom" else "Top"
            return Plan(route="sql", table=info.name, sql=sql, label=f"{word} {limit} rows by {measure}{suffix}",
                        kind="rows", measure=measure, limit=limit)

        if agg == "count":
            sql = f"SELECT COUNT(*) AS \"count\" FROM {table}{where}"
            return Plan(route="sql", table=info.name, sql=sql, label=f"Number of records in {info.name}{suffix}",
                        kind="scalar", agg="count")

        if not measure:
            return self._ask_which(info, "Which numeric column should I use?")
        use = agg if agg in SQL_FUNCS else "sum"
        sql = f"SELECT {SQL_FUNCS[use]}({_quote(measure)}) AS \"value\" FROM {table}{where}"
        label = f"{AGG_NAMES[use]} {measure.replace('_', ' ')}{suffix}"
        return Plan(route="sql", table=info.name, sql=sql, label=label, kind="scalar", agg=use, measure=measure)

"""
SQL Executor node — loads CSV into in-memory SQLite,
runs each KPI SQL query, records QueryResult per KPI
(dataframe, row count, columns, pass/fail + error message).
"""
from agent.state import AgentState


def run_sql_executor(state: AgentState) -> AgentState:
    # TODO: sqlite3 in-memory DB, execute KPI queries, capture results
    raise NotImplementedError

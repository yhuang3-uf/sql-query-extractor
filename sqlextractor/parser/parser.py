import sqlite3
# TODO Run the input string through SQLite and check for
# a syntax error.

class SqlSyntaxError(RuntimeError):
    """
    Raised when there is a syntax error with the parsed SQL
    """
    def __init__(self) -> None:
        pass

def check_valid(sql_query: str) -> bool:
    """
    Checks whether the SQL query has valid syntax

    :return: The input string.
    :raises SqlSyntaxError: IF the syntax of the query is invalid
    """
    tempdb: sqlite3.Connection = sqlite3.connect(":memory:")
    try:
        tempdb.execute(sql_query)
    except sqlite3.OperationalError as e:
        if "syntax error" in str(e):
            return False
    return True

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
    pass

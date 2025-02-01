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

    :return: True if valid, False if not
    """
    if sql_query.strip() == "":
        # Empty strings, while technically valid SQL, are not helpful for the
        # purposes of this project.
        return False
    if sql_query.lstrip()[:2] in ("--", "/*") or sql_query.lstrip()[0] == "#":
        # All-comment SQL strings are useless as well.
        return False
    if sql_query.replace(";", "").strip() == "":
        # All-semicolon strings are, while technically valid SQL, not helpful either.
        return False
    # First, manually filter out commands that might mess with the SQLITE database
    if sql_query.lower() in ("end", "vacuum", "commit", "commit;", "begin", "rollback"):
        return False
    if "vacuum" == sql_query.lower()[:6]:
        return False

    tempdb: sqlite3.Connection = sqlite3.connect(":memory:")
    try:
        tempdb.execute(sql_query)
    except sqlite3.OperationalError as e:
        if "syntax error" in str(e):
            return False
        elif "unrecognized token" in str(e):
            # Not valid SQL
            return False
        elif "incomplete input" in str(e):
            return False
        elif "unknown database" in str(e):
            return True
        elif "no such table" in str(e):
            return True
        elif "no such function" in str(e):
            # TODO Mark as False in the future once you implement concat
            return True
        elif "no tables specified" in str(e):
            # TODO Mark as False in the future once you implement concat
            return False
        elif "no such column" in str(e):
            return True
        print(sql_query)
        raise e
    except sqlite3.ProgrammingError as e:
        if "contains a null character" in str(e):
            # Not valid SQL
            return False
        elif "Incorrect number of bindings supplied" in str(e):
            # Seems to be valid SQL
            return True
        else:
            # Well, we weren't expecting this...
            raise e
    return True

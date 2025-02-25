import sqlite3
import psycopg2 
import sys

class SqlSyntaxError(RuntimeError):
    """
    Raised when there is a syntax error with the parsed SQL
    """
    def __init__(self) -> None:
        pass

def check_valid_pglast_postgres(sql_query: str):
    '''
    Checks if query is valid by 1. Checking it passes parsing with `pglast` (check_valid_pglast) 2. If 1 is true, executing in PostgreSQL (check_valid_postgres)

    Requires `pglast` and `psycopg2` to be installed

    This function exists because 1. The pglast check is too broad (returns queries that will actually fail) and 2. The PostgreSQL execution check is too time consuming to run with each string

    :return: True if SQL is valid, False if not
    '''
    if (check_valid_pglast(sql_query)):
        return check_valid_postgres(sql_query)
    else:
        return False

def check_valid_pglast(sql_query: str) -> bool:
    """
    Checks whether an SQL query has valid syntax using the `pglast` module.

    Requires `pglast` to be installed

    :return: True if SQL is valid, False if not.
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
    # TODO Filter out other statements like "begin" and "end" which are not useful
    import pglast  # type: ignore[import-untyped]
    try:
        pglast.parse_sql(sql_query)
    except pglast.parser.ParseError:
        # Oops, parsing failed.
        return False
    return True

def check_valid_postgres(sql_query: str) -> bool:
    '''
    Checks whether an SQL query has valid syntax by trying to execute it in a PostgreSQL docker instance

    Requires `psycopg2` to be installed and postgres running in docker
    To run postgres in docker: docker run --rm -d -p 5432:5432 --name temp_pg -e POSTGRES_PASSWORD=secret postgres
    To stop postgres in docker: docker stop temp_pg

    :return: True if SQL is valid, False if not
    '''
    conn = psycopg2.connect(
        dbname="postgres",
        user="postgres",
        password="secret",
        host="localhost",
        port="5432"
    )

    cursor = conn.cursor()
    cursor.execute("DROP SCHEMA public CASCADE;")
    cursor.execute("CREATE SCHEMA public;")

    valid_query = False

    try:
        cursor.execute(sql_query)
        valid_query = True
    except psycopg2.errors.UndefinedTable as e:
        valid_query = True
    except Exception as e:
        pass

    conn.close()
    cursor.close()

    return valid_query

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
    if sql_query.lower() in ("end", "vacuum", "begin", "rollback", "rollback;"):
        return False
    if "vacuum" == sql_query.lower()[:6]:
        return False
    if "commit" == sql_query.lower()[:6]:
        return False

    tempdb: sqlite3.Connection = sqlite3.connect(":memory:")
    try:
        try:
            tempdb.execute(sql_query)
        except sqlite3.Warning as e:
            if "SQL is of wrong type" in str(e):
                print("SQL query is of wrong type: " + repr(sql_query), file=sys.stderr)
                return False
            if "You can only execute one statement at a time" not in str(e):
                raise e
        tempdb.executescript(sql_query)
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
        elif "duplicate column name" in str(e):
            # Possibly a prepared statement/format string
            return True
        elif "no such collation sequence" in str(e):
            return True
        elif "no such table" in str(e):
            return True
        elif "no such database" in str(e):
            return True
        elif "no such index" in str(e):
            return True
        elif "no such module" in str(e):
            return True
        elif "no such trigger" in str(e):
            return True
        elif "no such view" in str(e):
            return True
        elif "no such savepoint" in str(e):
            return True
        elif "already exists" in str(e):
            return True
        elif "no such function" in str(e):
            # TODO Mark as False in the future once you implement concat
            return False
        elif "no tables specified" in str(e):
            # TODO Mark as False in the future once you implement concat
            return False
        elif "no such column" in str(e):
            return True
        elif "unable to open database" in str(e):
            return True
        elif "unknown table option" in str(e):
            # This is valid SQL in other dialects, but not in SQLite.
            return False
        elif "not currently supported" in str(e):
            # This indicates features that might be supported in future vesions of SQLite
            return True
        elif "not authorized" in str(e):
            # SQL query valid, but not allowed in current context
            return True
        elif "cannot commit - no transaction is active" in str(e):
            return True
        elif "unknown or unsupported join type" in str(e):
            # SQLite may not support this join type, but other flavors might.
            return True
        elif "table" in str(e) and "may not be modified" in str(e):
            return True
        elif "database" in str(e) and "already in use" in str(e):
            return True
        elif "cannot rollback" in str(e):
            # Rollback failed - probably this is a valid query.
            return True

        # Since we've covered ~99% of cases already, we'll just return False and not bother.
        print("Got unknown error when processing SQL query: " + str(sql_query), file=sys.stderr)
        print("The error is \"" + str(e) + "\"", file=sys.stderr)
        return False
    except sqlite3.ProgrammingError as e:
        if "contains a null character" in str(e):
            # Not valid SQL
            return False
        elif "Incorrect number of bindings supplied" in str(e):
            # Seems to be valid SQL
            return True
        else:
            # Well, we weren't expecting this...
            print("Got unknown error when processing SQL query: " + str(sql_query), file=sys.stderr)
            print("The error is \"" + str(e) + "\"", file=sys.stderr)
            return False
    return True

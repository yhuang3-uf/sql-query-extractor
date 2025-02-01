"""
A unit test file for Python
"""

import sqlite3

if __name__ == "__main__":
    # Make a sample print statement.
    print("Hello, world!")
    if input("Please enter \"abc\" ") == "abc":
        print("Success")
    else:
        print("Failure")
    
    print('"', "'")

    # Start reading the "database"
    database: sqlite3.Connection = sqlite3.connect("mydatabase.db")
    database.execute("SELECT username, password FROM users WHERE admin=0;")
    database.close()


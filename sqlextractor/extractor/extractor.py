import ast
import pathlib
import re
import typing

class ParsingError(Exception):
    """
    Encountered an issue with parsing the source code.
    """
    def __init__(self, line: int, line_content: str, character: int,
                 message: str) -> None:
        super().__init__("Failed to parse - " + message + "\n" + 
                         "At line " + str(line) + " character " + str(character) + "\n" + 
                         line_content + "\n" + 
                         (' ' * character) + "^")

class Extractor:
    """
    The base class to extract SQL queries.

    Abstract. Not meant to be directly instantiated
    """
    TOKEN_ADD: str = "add"
    """The addition token (or equivalent)"""
    TOKEN_CONCAT: str = "concat"
    """The string concat token (or equivalent)"""
    TOKEN_IDENTIFIER: str = "identifier"
    """Identifier-like constructs"""
    TOKEN_STRING: str = "string"
    """Represents a string literal"""
    TOKEN_NEWLINE: str = "newline"
    """Represents a newline"""
    TOKEN_UNKNOWN: str = "unknown"
    """Represents an unknown token"""

    def __init__(self, source: str) -> None:
        """
        :param source: The source code of the file to extract candidate 
        SQL queries from.
        """
        self.__source: str = source
    
    def extract_strings(self) -> list[str]:
        """
        Extracts SQL queries from the source code.

        :return: A list of strings that were found in the
        source code.
        """
        tokens: list[tuple[str, str, int, int, int]] = self.tokenize()
        return self.parse(tokens)
    
    def parse(self, tokens: list[tuple[str, str, int, int, int]]) -> list[str]:
        """
        Parses the tokens to return a list of strings in the program.
        :param tokens: The list of tokens to parse
        """
        raise NotImplementedError("Subclasses of Extractor should implement" + 
                "parse()")

    def tokenize(self) -> list[tuple[str, str, int, int, int]]:
        """
        Tokenizes the source code. A token is a tuple of
        (token_type, token_literal, line_number, character_number, token_index)

        The source code is stored in `Extractor.source`.
        """
        raise NotImplementedError("Subclasses of Extractor should implement" + 
                "tokenize()")
    
    @property
    def source(self) -> str:
        """The source code of the file to extract candidate SQL queries from"""
        return self.__source

    @staticmethod
    def extract_bigquery(repo_name: str, path: str, content: str) -> list[str]:
        """
        Extracts strings from a file in BigQuery.

        Chooses the correct extractor, extracts SQL queries from it, and
        returns the result.

        :param repo_name: The name of the repository
        :param path: The path to the file within the repository
        :param content: The content of the file.
        """
        file_extension: str = pathlib.Path(path).suffix.lower()
        extractor: typing.Optional[Extractor] = None
        if file_extension == ".py":
            extractor = PythonExtractor(content)
        elif file_extension == ".js":
            extractor = JavaScriptExtractor(content)
        elif file_extension == ".php":
            extractor = PHPExtractor(content)
        else:
            raise ValueError("Unknown file type \"" + file_extension + "\"")
        assert extractor is not None
        return extractor.extract_strings()


class PythonExtractor(Extractor):
    """
    Extracts strings from Python files
    """
    def parse(self, tokens: list[tuple[str, str, int, int, int]]) -> list[str]:

        def parse_string(token: tuple[str, str, int, int, int]) -> str:
            """Parses a Python string."""
            try:
                return ast.literal_eval("'" + token[1] + "'")
            except SyntaxError:
                # Find the last line break
                last_line_break = token[4]
                next_line_break = token[4]
                if token[4] >= len(self.source):
                    raise ParsingError(token[2], "", 0, "Potential unterminated string literal")
                while last_line_break > 0 and self.source[last_line_break] != '\n':
                    last_line_break -= 1
                while next_line_break < len(self.source) - 1 and self.source[next_line_break] != '\n':
                    next_line_break += 1
                
                raise ParsingError(token[2], self.source[last_line_break+1:next_line_break], token[3], "Failed to parse string")

        strings: list[str] = []
        i: int = 0
        while i < len(tokens):
            current_string: str = ""

            while i < len(tokens):
                if tokens[i][0] == (self.TOKEN_STRING):
                    current_string += parse_string(tokens[i])
                elif tokens[i][0] == "rawstring":
                    current_string += tokens[i][1]
                else:
                    # Not a string, let's loop again.
                    break
                

                # Advance to the next token
                i += 1
                if i >= len(tokens):
                    # We've reached the end.
                    break
                if tokens[i][0] in (self.TOKEN_STRING, "rawstring"):
                    # Proceed to next token as planned
                    pass
                elif tokens[i][0] in (self.TOKEN_ADD,):
                    # This is an addition token. There might be something
                    # interesting here.
                    string_to_append: str = ""
                    """The string to append to the main string"""
                    if i+1 >= len(tokens):
                        # We've reached the end.
                        break
                    # Peek at the next token.
                    while tokens[i+1][0] == self.TOKEN_IDENTIFIER:
                        # Advance to the next token, which is an identifier
                        i += 1
                        if i+1 >= len(tokens):
                            # We've reached the end of the tokens.
                            break
                        # Peek at the next token again
                        if tokens[i+1][0] == self.TOKEN_ADD:
                            # Okay, let's loop again.
                            # Add a placeholder to the string
                            string_to_append += "'placeholder'"
                            # Advance to the next token.
                            i += 1
                            # Check if it is a string. If so, break out of this loop.
                            if tokens[i+1][0] in (self.TOKEN_STRING, "rawstring"):
                                current_string += string_to_append
                                break
                            # Okay, this token is not a string.
                            # Let's go back to the beginning of the loop.
                            continue
                        else:
                            # Invalid token
                            string_to_append = ""
                            break
                else:
                    # We don't know this token, but it's not a string.
                    # So we don't care.
                    break
            
            # Add the current string to the list, if it is nonempty
            if current_string != "":
                strings.append(current_string)

            i += 1
        
        return strings

    def tokenize(self) -> list[tuple[str, str, int, int, int]]:
        tokens_list: list[tuple[str, str, int, int, int]] = []
        
        index: int = 0
        """The index we are at in the source code"""
        
        last_line_break: int = 0
        """The last time we had a line break"""

        line_number: int = 0
        """The line number we are at in the source code"""

        while index < len(self.source):
            if self.source[index] == '#':
                # Inside a comment
                while index < len(self.source) and self.source[index] != '\n':
                    index += 1
                line_number += 1
                last_line_break = index
            elif self.source[index] == '+':
                # Addition token
                index += 1
                tokens_list.append((self.TOKEN_ADD, '+', line_number, 
                                    index - last_line_break, index))
            elif self.source[index] in ("\"", "\'") or \
                    self.source[index:index+2] in ("u\"", "U\"", "u'", "U'") or \
                    self.source[index:index+2] in ("f\"", "F\"", "f'", "F'"):
                # Normal string with escapes
                # TODO Separate f strings into their own thing
                close_string_char: str = self.source[index]
                triple_string: bool = False
                """Whether the string is a triple-quoted string"""
                index += 1
                if index >= len(self.source):
                    raise ParsingError(line_number, self.source[last_line_break:], len(self.source) - 1, 
                                       "Unterminated string literal")
                if close_string_char in ("\"", "'"):
                    # Check for triple quote
                    if self.source[index] == close_string_char and \
                            index+1 < len(self.source) and \
                            self.source[index+1] == close_string_char:
                        # This is a triple quoted string
                        triple_string = True
                        index += 2
                else:
                    close_string_char = self.source[index]
                    index += 1
                current_string: str = ""
                while index < len(self.source):
                    if triple_string:
                        if self.source[index:index+3] == (close_string_char * 3):
                            # The string is finished
                            index += 3
                            break
                    elif self.source[index] == close_string_char:
                        # The string is finished
                        index += 1
                        break
                    if self.source[index] == "\\":
                        # Start of an escape sequence
                        current_string += self.source[index:index+2]
                        index += 2
                    else:
                        # Escape line breaks inside a triple string
                        if triple_string and self.source[index] == "\r":
                            current_string += "\\r"
                        if triple_string and self.source[index] == "\n":
                            line_number += 1
                            last_line_break = index
                            current_string += "\\n"
                        elif self.source[index] == "'":
                            current_string += "\\'"
                        elif self.source[index] == '"':
                            current_string += '\\"'
                        else:
                            current_string += self.source[index]
                        index += 1
                tokens_list.append((self.TOKEN_STRING, current_string, line_number, 
                                    index - last_line_break, index))
            elif self.source[index:index+2] in ("r\"", "R\"", "r'", "R'"):
                # Raw string, no escapes
                close_string_char = self.source[index+1]
                current_rawstring: str = ""
                index += 2
                while index < len(self.source) and self.source[index] != close_string_char:
                    current_rawstring += self.source[index]
                    index += 1
                index += 1
                tokens_list.append(("rawstring", current_rawstring, line_number, 
                                    index - last_line_break, index))
            elif re.match(r"[A-Za-z_]", self.source[index]):
                # This is an identifier
                current_identifier: str = self.source[index]
                index += 1
                while index < len(self.source) and re.match(r"[A-Za-z0-9_]", self.source[index]):
                    current_identifier += self.source[index]
                    index += 1
                tokens_list.append((self.TOKEN_IDENTIFIER, current_identifier, line_number, 
                                    index - last_line_break, index))
            elif self.source[index] in ('\n'):
                line_number += 1
                index += 1
            elif self.source[index] in (' ', '\t', '\r'):
                # A space is not a token (we ignore indents for now)
                index += 1
            else:
                # Unknown token
                tokens_list.append((self.TOKEN_UNKNOWN, self.source[index], line_number,
                                    index - last_line_break, index))
                index += 1
        
        return tokens_list

class JavaScriptExtractor(Extractor):
    """
    Extracts strings from JavaScript files
    """
    def parse(self, tokens: list[tuple[str, str, int, int, int]]) -> list[str]:
        strings: list[str] = []
        i: int = 0

        while i < len(tokens):
            current_string: str = ""

            while i < len(tokens):
                if tokens[i][0] == (self.TOKEN_STRING):
                    current_string += tokens[i][1]
                else:
                    # Not a string, let's loop again.
                    break
                
                # Advance to the next token
                i += 1
                if i >= len(tokens):
                    # We've reached the end.
                    break

                table_number: int = 1
                placeholder_number: int = 1

                # Loop through concatenation
                while i < len(tokens) and tokens[i][0] in (self.TOKEN_ADD):
                    string_to_append: str = ""

                    if (i+1 >= len(tokens)):
                        break
                    elif (tokens[i+1][0] == self.TOKEN_NEWLINE): # Add newline to string
                        current_string += "\n"
                        i += 1
                        while tokens[i+1][0] == self.TOKEN_NEWLINE:
                            i += 1
                    
                    if (i+1 >= len(tokens)):
                        break
                    elif (tokens[i+1][0] == self.TOKEN_IDENTIFIER): # Add tbl or placeholder to string in place of concatenated identifier
                        while i+1 < len(tokens) and tokens[i+1][0] == self.TOKEN_IDENTIFIER:
                            i += 1
                        
                        current_string_rstrip = current_string.rstrip()
                        if (current_string_rstrip.upper().endswith(tuple(["FROM", "UPDATE", "INTO", "TABLE" , "JOIN", "TABLE IF NOT EXISTS"]))):
                            string_to_append = "tbl" + str(table_number)
                            table_number += 1
                        else:
                            string_to_append = "placeholder" + str(placeholder_number)
                            placeholder_number += 1

                    elif (tokens[i+1][0] == self.TOKEN_STRING): # append string to string
                        string_to_append = tokens[i+1][1]
                        i += 1
                    
                    current_string += string_to_append
                    i += 1
                    
            # Add the current string to the list, if it is nonempty
            if current_string != "":
                strings.append(current_string)

            i += 1
        
        # Filter out/prepare strings
        filtered_strings = []
        for string in strings:
            # Check for valid postgres
            if (string.find(" ") != -1 and len(string) > 5):
                string = string.replace("\\\"", "\"")
                string = string.replace ("\\'", "'")
                string = string.replace("?", "'placeholder_value'")

                upper = string.upper()

                if (self.check_sql_keyword(string)) \
                    and len(string) < 1000 and string.find("<") != 0 and \
                    upper != "SELECT ALL" and string.find(" ") != -1 and upper != "SHOW ALL" and \
                    upper != "LOCK RATIO" and upper != "LOCK UNLOCK":
                        filtered_strings.append(string)
        
        return filtered_strings

    def tokenize(self) -> list[tuple[str, str, int, int, int]]:
        tokens_list: list[tuple[str, str, int, int, int]] = []
        
        index: int = 0
        """The index we are at in the source code"""
        
        last_line_break: int = 0
        """The last time we had a line break"""

        line_number: int = 0
        """The line number we are at in the source code"""

        # Find keywords
        next_index = self.find_next_keyword(index)

        while next_index != None and index < len(self.source):
            index = next_index - 1

            while index < len(self.source):
                if self.source[index:index+2] == ("//"):
                    # Inside a single-line comment
                    while index < len(self.source) and self.source[index] != '\n':
                        index += 1
                    line_number += 1
                    last_line_break = index
                elif self.source[index:index+2] == ("/*"):    
                    # Inside a block comment
                    while index < len(self.source) and self.source[index:index+2] != ("*/"):
                        if (self.source[index] != '\n'):
                            index += 1
                        else:
                            line_number += 1
                            last_line_break = index
                            index += 1               
                elif self.source[index] == '+':
                    # Addition token
                    index += 1
                    tokens_list.append((self.TOKEN_ADD, '+', line_number, 
                                        index - last_line_break, index))
                elif self.source[index] in ("\"", "\'"):
                    # Normal string with escapes
                    close_string_char: str = self.source[index]
                    index += 1
                    if index >= len(self.source):
                        raise ParsingError(line_number, self.source[last_line_break:], len(self.source) - 1, 
                                        "Unterminated string literal")
                    current_string: str = ""
                    start_index = index
                    while index < len(self.source):
                        if self.source[index] == close_string_char:
                            # The string is finished
                            index += 1
                            break
                        if self.source[index] == "\\":
                            # Start of an escape sequence
                            index += 2
                        else:
                            index += 1

                    current_string = self.source[start_index:index-1]
                    tokens_list.append((self.TOKEN_STRING, current_string, line_number, 
                                        index - last_line_break, index))
                elif re.match(r"[A-Za-z_().$0-9]", self.source[index]):
                    # This is an identifier
                    current_identifier: str = "" #self.source[index]
                    start_index = index
                    index += 1
                    while index < len(self.source) and re.match(r"[A-Za-z.()0-9_]", self.source[index]):
                        index += 1
                    current_identifier = self.source[start_index:index]

                    #print(current_identifier)
                    tokens_list.append((self.TOKEN_IDENTIFIER, current_identifier, line_number, 
                                        index - last_line_break, index))
                elif self.source[index] in ('\n'):
                    tokens_list.append((self.TOKEN_NEWLINE, "\n", line_number, 
                                        index - last_line_break, index))
                    line_number += 1
                    index += 1
                elif self.source[index] in (' ', '\t', '\r'):
                    # A space is not a token (we ignore indents for now)
                    index += 1
                else:
                    # Unknown token
                    tokens_list.append((self.TOKEN_UNKNOWN, self.source[index], line_number,
                                        index - last_line_break, index))
                    index += 1
                    break;
            if index == next_index:
                index += 1
            next_index = self.find_next_keyword(index)

        return tokens_list


    def find_next_keyword(self, index):
        # Finds index of next SQL keyword

        # List of SQL keywords that can start a statement in PostgreSQL
        sql_keywords = [
            "SELECT", "WITH", "INSERT", "UPDATE", "DELETE", "MERGE", "CREATE", "ALTER", "DROP", "TRUNCATE",
            "BEGIN", "COMMIT", "ROLLBACK", "SAVEPOINT", "RELEASE", "PREPARE TRANSACTION", "GRANT", "REVOKE",
            "LOCK", "ANALYZE", "EXPLAIN", "DISCARD", "SET", "RESET", "SHOW", "VACUUM", "CHECKPOINT",
            "CLUSTER", "REINDEX", "LISTEN", "NOTIFY", "UNLISTEN", "DO"
        ]
        
        # regex pattern that matches any of these keywords
        pattern = re.compile(r'\b(' + '|'.join(sql_keywords) + r')\b', re.IGNORECASE)
        
        match = pattern.search(self.source[index:])
        
        return match.start() + index if match else None

    def check_sql_keyword(self, string):
        # Checks if string has a SQL keyword

        # List of SQL keywords that can start a statement in PostgreSQL
        sql_keywords = [
            "SELECT ", "WITH ", "INSERT ", "UPDATE ", "DELETE ", "MERGE ", "CREATE ", "ALTER ", "DROP ", "TRUNCATE ",
            "BEGIN ", "COMMIT ", "ROLLBACK ", "SAVEPOINT ", "RELEASE ", "PREPARE TRANSACTION ", "GRANT ", "REVOKE ",
            "LOCK ", "ANALYZE ", "EXPLAIN ", "DISCARD ", "SET ", "RESET ", "SHOW ", "VACUUM ", "CHECKPOINT ",
            "CLUSTER ", "REINDEX ", "LISTEN ", "NOTIFY ", "UNLISTEN ", "DO "
        ]
        
        #pattern that matches any of these keywords
        pattern = re.compile(r'\b(' + '|'.join(sql_keywords) + r')\b', re.IGNORECASE)
        
        match = pattern.search(string)
        
        return True if match else False
    
class PHPExtractor(Extractor):
    """
    Extracts strings from JavaScript files
    """
    def parse(self, tokens: list[tuple[str, str, int, int, int]]) -> list[str]:
        strings: list[str] = []
        i: int = 0

        while i < len(tokens):
            current_string: str = ""

            table_number: int = 1
            placeholder_number: int = 1

            while i < len(tokens):
                if tokens[i][0] == (self.TOKEN_STRING):
                    current_string += tokens[i][1]
                else:
                    # Not a string, let's loop again.
                    break
                
                # Advance to the next token
                i += 1
                if i >= len(tokens):
                    # We've reached the end.
                    break


                # Loop through concatenation
                while i < len(tokens) and tokens[i][0] in (self.TOKEN_ADD):
                    string_to_append: str = ""

                    if (i+1 >= len(tokens)):
                        break
                    elif (tokens[i+1][0] == self.TOKEN_NEWLINE): # Add newline to string
                        current_string += "\n"
                        i += 1
                        while tokens[i+1][0] == self.TOKEN_NEWLINE:
                            i += 1
                    
                    if (i+1 >= len(tokens)):
                        break
                    elif (tokens[i+1][0] == self.TOKEN_IDENTIFIER): # Add tbl or placeholder to string in place of concatenated identifier
                        while i+1 < len(tokens) and tokens[i+1][0] == self.TOKEN_IDENTIFIER:
                            i += 1
                        
                        current_string_rstrip = current_string.rstrip()
                        if (current_string_rstrip.upper().endswith(tuple(["FROM", "UPDATE", "INTO", "TABLE" , "JOIN", "TABLE IF NOT EXISTS"]))):
                            string_to_append = "tbl" + str(table_number)
                            table_number += 1
                        else:
                            string_to_append = "placeholder" + str(placeholder_number)
                            placeholder_number += 1
                        

                        if (i + 3 < len(tokens) and tokens[i+1][0] == self.TOKEN_STRING and tokens[i+2][0] == self.TOKEN_UNKNOWN and tokens[i+3][0] == self.TOKEN_ADD):
                            i += 2
                        elif (i + 4 < len(tokens) and tokens[i+1][0] == self.TOKEN_STRING and tokens[i+2][0] == self.TOKEN_UNKNOWN and tokens[i+3][0] == self.TOKEN_IDENTIFIER and tokens[i+4][0] == self.TOKEN_ADD):
                            i += 3

                    elif (tokens[i+1][0] == self.TOKEN_STRING): # append string to string
                        string_to_append = tokens[i+1][1]
                        i += 1
                    
                    current_string += string_to_append
                    i += 1
                    
            # Add the current string to the list, if it is nonempty
            if current_string != "":
                current_string = self.filter_query_php(current_string, table_number, placeholder_number)
                strings.append(current_string)

            i += 1
        
        valid = []
        invalid = []
        # Filter out/prepare strings
        filtered_strings = []
        for string in strings:
            # Check for valid postgres
            if (string.find(" ") != -1 and len(string) > 5):
                string = string.replace("\\\"", "\"")
                string = string.replace ("\\'", "'")
                string = string.replace("?", "'placeholder_value'")

                upper = string.upper()

                if (self.check_sql_keyword(string)) \
                    and len(string) < 1000 and string.find("<") != 0 and upper != "SELECT ALL":
                        filtered_strings.append(string)

        return filtered_strings

    def tokenize(self) -> list[tuple[str, str, int, int, int]]:
        tokens_list: list[tuple[str, str, int, int, int]] = []
        
        index: int = 0
        """The index we are at in the source code"""
        
        last_line_break: int = 0
        """The last time we had a line break"""

        line_number: int = 0
        """The line number we are at in the source code"""

        # Find keywords
        next_index = self.find_next_keyword(index)

        while next_index != None and index < len(self.source):
            index = next_index - 1

            while index < len(self.source):
                if self.source[index:index+2] == "//":
                    # Inside a single-line comment
                    while index < len(self.source) and self.source[index] != '\n':
                        #print(self.source[index])
                        index += 1
                    line_number += 1
                    last_line_break = index
                elif self.source[index:index+2] == ("/*"):    
                    # Inside a block comment
                    while index < len(self.source) and self.source[index:index+2] != ("*/"):
                        if (self.source[index] != '\n'):
                            index += 1
                        else:
                            line_number += 1
                            last_line_break = index
                            index += 1               
                elif self.source[index] == '.':
                    # Addition token
                    index += 1
                    tokens_list.append((self.TOKEN_ADD, '.', line_number, 
                                        index - last_line_break, index))
                elif self.source[index] in ("\"", "\'"):
                    # Normal string with escapes
                    close_string_char: str = self.source[index]
                    index += 1
                    if index >= len(self.source):
                        raise ParsingError(line_number, self.source[last_line_break:], len(self.source) - 1, 
                                        "Unterminated string literal")
                    current_string: str = ""
                    start_index = index
                    while index < len(self.source):
                        if self.source[index] == close_string_char:
                            # The string is finished
                            index += 1
                            break
                        if self.source[index] == "\\":
                            # Start of an escape sequence
                            index += 2
                        else:
                            index += 1

                    current_string = self.source[start_index:index-1]
                    tokens_list.append((self.TOKEN_STRING, current_string, line_number, 
                                        index - last_line_break, index))
                elif re.match(r"[A-Za-z_()$0-9]", self.source[index]):
                    # This is an identifier
                    current_identifier: str = "" #self.source[index]
                    start_index = index
                    index += 1
                    while index < len(self.source) and re.match(r"[A-Za-z0-9_$(){}\[\]>\-]", self.source[index]):
                        index += 1
                    current_identifier = self.source[start_index:index]

                    tokens_list.append((self.TOKEN_IDENTIFIER, current_identifier, line_number, 
                                        index - last_line_break, index))
                elif self.source[index] in ('\n', '\r'):
                    tokens_list.append((self.TOKEN_NEWLINE, "\n", line_number, 
                                        index - last_line_break, index))
                    line_number += 1
                    index += 1
                elif self.source[index] in (' ', '\t'):
                    # A space is not a token (we ignore indents for now)
                    index += 1
                else:
                    # Unknown token
                    tokens_list.append((self.TOKEN_UNKNOWN, self.source[index], line_number,
                                        index - last_line_break, index))
                    index += 1

                    if (self.source[index-1] != ']'):
                        break;
            
            if index == next_index:
                index += 1
            next_index = self.find_next_keyword(index)

        return tokens_list


    def find_next_keyword(self, index):
        # List of SQL keywords that can start a statement in PostgreSQL
        sql_keywords = [
            "SELECT", "WITH", "INSERT", "UPDATE", "DELETE", "MERGE", "CREATE", "ALTER", "DROP", "TRUNCATE",
            "BEGIN", "COMMIT", "ROLLBACK", "SAVEPOINT", "RELEASE", "PREPARE TRANSACTION", "GRANT", "REVOKE",
            "LOCK", "ANALYZE", "EXPLAIN", "DISCARD", "SET", "RESET", "SHOW", "VACUUM", "CHECKPOINT",
            "CLUSTER", "REINDEX", "LISTEN", "NOTIFY", "UNLISTEN", "DO"
        ]
        
        # Regex pattern that matches any of these keywords
        pattern = re.compile(r'\b(' + '|'.join(sql_keywords) + r')\b', re.IGNORECASE)
        
        match = pattern.search(self.source[index:])
        
        if match:
            keyword_index = match.start() + index
            last_newline = self.source.rfind('\n', index, keyword_index)
            next_newline = self.source.find('\n', keyword_index)
            
            next_line = self.source[last_newline:next_newline].strip()
            if (len(next_line) > 0 and next_line[0] == '*'):
                #print(next_line)
                return next_newline + 1

            return last_newline if last_newline != -1 else index
        
        return None

    def check_sql_keyword(self, string):
        # Checks if string has a SQL keyword

        # List of SQL keywords that can start a statement in PostgreSQL
        sql_keywords = [
            "SELECT ", "WITH ", "INSERT ", "UPDATE ", "DELETE ", "MERGE ", "CREATE ", "ALTER ", "DROP ", "TRUNCATE ",
            "BEGIN ", "COMMIT ", "ROLLBACK ", "SAVEPOINT ", "RELEASE ", "PREPARE TRANSACTION ", "GRANT ", "REVOKE ",
            "LOCK ", "ANALYZE ", "EXPLAIN ", "DISCARD ", "SET ", "RESET ", "SHOW ", "VACUUM ", "CHECKPOINT ",
            "CLUSTER ", "REINDEX ", "LISTEN ", "NOTIFY ", "UNLISTEN ", "DO "
        ]
        
        # Pattern that matches any of these keywords
        pattern = re.compile(r'\b(' + '|'.join(sql_keywords) + r')\b', re.IGNORECASE)
        
        match = pattern.search(string)
        
        return True if match else False
    
    def filter_query_php(self, string, table_number, placeholder_number):
        # Filters queries 

        # ` is not used in Postgres
        string = string.replace("`", "'")

        # : is not used in Postgres
        string = string.replace(":", "")

        # Replace variables
        pattern = r'((\{|\$)[^\s,\'\"]+)' # {variables} or $variables in the string!
    
        matches = re.findall(pattern, string)
        for match in matches:
            string = string.replace(match[0], f"placeholder{placeholder_number}")
            placeholder_number += 1
        
        # Replace %d
        pattern = r'%d'
        matches = re.findall(pattern, string)
        for match in matches:
            string = string.replace(match, f"placeholder_digit{placeholder_number}")
            placeholder_number += 1
        
        # Replace %s
        pattern = r'%s'
        matches = re.findall(pattern, string)
        for match in matches:
            string = string.replace(match, f"'placeholder_string{placeholder_number}'")
            placeholder_number += 1

        # Removing '' from table names (Doesn't work in postgres)
        pattern = r"(?<=FROM\s)'(\w+)'|(?<=JOIN\s)'(\w+)'|(?<=INTO\s)'(\w+)'|(?<=UPDATE\s)'(\w+)'|(?<=TABLE\s)'(\w+)'|(?<=TABLE IF EXISTS\s)'(\w+)'(?<=DROP\s)'(\w+)'|(?<=FROM\s)'\s(\w+)\s'|(?<=JOIN\s)'\s(\w+)\s'|(?<=INTO\s)'\s(\w+)\s'|(?<=UPDATE\s)'\s(\w+)\s'|(?<=TABLE\s)'\s(\w+)\s'|(?<=TABLE IF EXISTS\s)'\s(\w+)\s'(?<=DROP\s)'\s(\w+)\s'"
        def replacequote(match):
            return match.group(0).replace("'", "")

        string = re.sub(pattern, replacequote, string, flags=re.IGNORECASE)


        return string
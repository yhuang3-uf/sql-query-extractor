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

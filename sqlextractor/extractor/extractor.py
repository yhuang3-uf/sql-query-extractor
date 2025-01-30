import ast
import pathlib
import re
import typing

class Extractor:
    """
    The base class to extract SQL queries.

    Abstract. Not meant to be directly instantiated
    """
    TOKEN_ADD: str = "add"
    TOKEN_CONCAT: str = "concat"
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
        tokens: list[tuple[str, str]] = self.tokenize()
        return self.parse(tokens)
    
    def parse(self, tokens: list[tuple[str, str]]) -> list[str]:
        """
        Parses the tokens to return a list of strings in the program.
        :param tokens: The list of tokens to parse
        """
        raise NotImplementedError("Subclasses of Extractor should implement" + 
                "parse()")

    def tokenize(self) -> list[tuple[str, str]]:
        """
        Tokenizes the source code. A token is a tuple of
        (token_type, token_literal)

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
        if file_extension == "py":
            extractor = PythonExtractor(content)
        else:
            raise ValueError("Unknown file type \"" + file_extension + "\"")
        assert extractor is not None
        return extractor.extract_strings()


class PythonExtractor(Extractor):
    """
    Extracts strings from Python files
    """
    def parse(self, tokens: list[tuple[str, str]]) -> list[str]:
        strings: list[str] = []
        for token in tokens:
            # TODO Implement string concat
            if token[0] in (self.TOKEN_STRING, "rawstring"):
                strings.append(ast.literal_eval("'" + token[1] + "'"))
        
        return strings

    def tokenize(self) -> list[tuple[str, str]]:
        tokens_list: list[tuple[str, str]] = []
        
        index: int = 0
        """The index we are at in the source code"""

        while index < len(self.source):
            if self.source[index] == '#':
                # Inside a comment
                while index < len(self.source) and self.source[index] != '\n':
                    index += 1
            elif self.source[index] == '+':
                # Addition token
                index += 1
                tokens_list.append((self.TOKEN_ADD, '+'))
            elif self.source[index] in ("\"", "\'") or \
                    self.source[index:index+2] in ("u\"", "U\"", "u'", "U'") or \
                    self.source[index:index+2] in ("f\"", "F\"", "f'", "F'"):
                # Normal string with escapes
                # TODO Separate f strings into their own thing
                close_string_char: str = self.source[index]
                triple_string: bool = False
                """Whether the string is a triple-quoted string"""
                index += 1
                if close_string_char in ("\"", "'"):
                    # Check for triple quote
                    if self.source[index] == close_string_char and \
                            self.source[index+1] == close_string_char:
                        # This is a triple quoted string
                        triple_string = True
                else:
                    close_string_char = self.source[index]
                    index += 1
                current_string: str = ""
                while index < len(self.source):
                    if triple_string:
                        if self.source[index:index+3] == (close_string_char * 3):
                            # The string is finished
                            break
                    elif self.source[index] == close_string_char:
                        # The string is finished
                        break
                    if self.source[index] == "\\":
                        # Start of an escape sequence
                        current_string += self.source[index:index+2]
                        index += 2
                    else:
                        current_string += self.source[index]
                        index += 1
                tokens_list.append((self.TOKEN_STRING, current_string))
            elif self.source[index:index+2] in ("r\"", "R\"", "r'", "R'"):
                # Raw string, no escapes
                close_string_char = self.source[index+1]
                current_rawstring: str = ""
                index += 2
                while index < len(self.source) and self.source[index] != close_string_char:
                    current_rawstring += self.source[index]
                    index += 1
                index += 1
                tokens_list.append(("rawstring", current_rawstring))
            elif re.match(r"[A-Za-z_]", self.source[index]):
                # This is an identifier
                current_identifier: str = self.source[index]
                index += 1
                while index < len(self.source) and re.match(r"[A-Za-z0-9_]", self.source[index]):
                    current_identifier += self.source[index]
                    index += 1
                tokens_list.append((self.TOKEN_IDENTIFIER, current_identifier))
            elif self.source[index] in (' ', '\t', '\r', '\n'):
                # A space is not a token (we ignore indents for now)
                index += 1
            else:
                # Unknown token
                tokens_list.append((self.TOKEN_UNKNOWN, self.source[index]))
                index += 1
        
        return tokens_list

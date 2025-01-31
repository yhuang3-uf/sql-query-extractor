import argparse
import gzip
import json
import pathlib
import sys
import typing

import sqlextractor

def main(argv: list[str]) -> int:
    argparser: argparse.ArgumentParser = argparse.ArgumentParser("Extracts SQL queries from BigQuery data")
    argparser.add_argument("--intermediate-dir", "-i", 
            default=pathlib.Path("extractqueries-temp"), type=pathlib.Path,
            help="Temporary directory to put intermediate products into")
    argparser.add_argument("input_directory", type=pathlib.Path,
            help="Path to the BigQuery data")
    parsedargs: dict[str, typing.Any] = vars(argparser.parse_args())
    
    # TODO Parallelize with the multiprocessing module. To do this, read
    # in the list of all files, then distribute the tasks among each
    # process.
    for input_file in parsedargs["input_directory"].iterdir():
        if input_file.suffix.lower() == ".gz":
            # Read the file in line by line
            with gzip.open(str(input_file), mode="r") as json_file:
                for json_line in json_file:
                    # The JSON should contain "repo_name", "path", and
                    # "content"
                    bigquery_result: dict = json.loads(json_line)
                    try:
                        program_strings: list[str] = sqlextractor.extractor.extractor.Extractor.extract_bigquery(
                            bigquery_result["repo_name"], 
                            bigquery_result["path"],
                            bigquery_result["content"]
                        )
                        print(program_strings)
                        sql_strings: list[str] = []
                        for program_string in program_strings:
                            if sqlextractor.parser.parser.check_valid(program_string):
                                sql_strings.append(program_string)
                        print(sql_strings)
                    except ValueError:
                        # Unrecognized file type. That's okay.
                        continue
                    except KeyError as e:
                        if str(e) == "content":
                            # No source associated with this file.
                            continue

    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))

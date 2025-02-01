import pathlib
import sys

import sqlextractor

def main(argv: list[str]) -> int:
    unit_tests_folder: pathlib.Path = pathlib.Path("unittests")
    for subfolder in unit_tests_folder.iterdir():
        print("Running \"" + str(subfolder.name) + "\" tests...")
        for unit_test in subfolder.iterdir():
            print("Running test \"" + str(unit_test.name) + "\"...")
            unit_test_file = open(unit_test, 'r')
            unit_test_content: str = unit_test_file.read()
            unit_test_file.close()
            extracted_strings: list[str] = sqlextractor.extractor.extractor.Extractor.extract_bigquery("", unit_test.name, unit_test_content)
            print(extracted_strings)
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))

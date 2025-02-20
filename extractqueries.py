import argparse
import csv
import ctypes
import gzip
import json
import multiprocessing
import multiprocessing.sharedctypes
import multiprocessing.synchronize
import pathlib
import queue
import signal
import sys
import time
import typing

import sqlextractor


class SignalHandler:
    """Handle signals gracefully"""
    def __init__(self) -> None:
        signal.signal(signal.SIGINT, self.request_stop)
        signal.signal(signal.SIGTERM, self.request_stop)
        self.stop_requested: bool = False
        """Whether the OS has requested that we stop."""

    def request_stop(self, signum, frame) -> None:
        self.stop_requested = True


def worker_process(file_queue: multiprocessing.Queue, 
                   files_completed: multiprocessing.sharedctypes.Synchronized,
                   sql_query_queue: multiprocessing.Queue,
                   exception_thrown: multiprocessing.synchronize.Event) -> None:
    """
    A single process that will be parallelized. Given a Queue of file names, this will
    process in parallel. Controller by the main thread.

    :param file_queue: A queue to store the names of the input files
    :param files_completed: A multiprocessing.Value object storing the number of
    processes completed.
    :param sql_query_queue: A queue to store the output SQL queries to be passed back
    to the main thread.
    :param exception_thrown: Whether an exception has been thrown.
    """
    while True:
        try:
            input_file: pathlib.Path = file_queue.get(timeout=1/65536)

            # Read the file in line by line
            with gzip.open(str(input_file), mode="r") as json_file:
                for json_line in json_file:
                    # The JSON should contain "repo_name", "path", and
                    # "content"
                    bigquery_result: dict = json.loads(json_line)
                    # print(bigquery_result["repo_name"], bigquery_result["path"])
                    try:
                        program_strings: list[str] = sqlextractor.extractor.extractor.Extractor.extract_bigquery(
                            bigquery_result["repo_name"], 
                            bigquery_result["path"],
                            bigquery_result["content"]
                        )
                        #print(program_strings)
                        sql_strings: list[str] = []
                        for program_string in program_strings:
                            # Strip the whitespace from the string.
                            program_string = program_string.strip()
                            if sqlextractor.parser.parser.check_valid_pglast_postgres(program_string):
                                sql_strings.append(program_string)
                        for sql_string in sql_strings:
                            sql_query_queue.put((bigquery_result["repo_name"], bigquery_result["path"], sql_string))
                    except sqlextractor.extractor.extractor.ParsingError:
                        # Failed to parse the code. Hopefully this doesn't happen
                        # too much.
                        pass
                    except ValueError as e:
                        # Unrecognized file type. That's okay.
                        pass
                    except KeyError as e:
                        if e.args[0] == "content":
                            # No source associated with this file.
                            pass
                        else:
                            exception_thrown.set()
                            raise e

            # Increase the total number of files completed.
            with files_completed.get_lock():
                files_completed.value += 1
        except queue.Empty:
            # All files complete
            break


def main(argv: list[str]) -> int:
    argparser: argparse.ArgumentParser = argparse.ArgumentParser("Extracts SQL queries from BigQuery data")

    argparser.add_argument("--force-overwrite", "-f", action="store_true",
            help="If specified, output files will be overwritten without prompting. " + 
            "Useful when running non-interactively.")
    argparser.add_argument("--intermediate-dir", "-i", 
            default=pathlib.Path("extractqueries-temp"), type=pathlib.Path,
            help="Temporary directory to put intermediate products into")
    argparser.add_argument("--process-count", "-p", default=2, type=int,
            help="Number of processes to start. For maximum efficiency, set this" + 
            " to the number of available CPU cores.")
    argparser.add_argument("input_directory", type=pathlib.Path,
            help="Path to the BigQuery data")
    argparser.add_argument("output_file", type=pathlib.Path,
            help="The CSV file to output the queries to")
    parsedargs: dict[str, typing.Any] = vars(argparser.parse_args())
    
    if parsedargs["output_file"].is_file():
        if not parsedargs["force_overwrite"] and \
                input("Overwrite file \"" + str(parsedargs["output_file"]) + "\"? [y/N] ").strip().lower() != 'y':
            print("Not overwriting file.")
            return 16
    elif parsedargs["output_file"].exists():
        print("ERROR: Expected \"" + str(parsedargs["output_file"]) + 
              "\" to be a file, but it is not.")
        print("Exiting...")
        return 16

    # Write the header line of the file.
    with open(parsedargs["output_file"], 'w') as outputcsvfile:
        outputcsvwriter = csv.writer(outputcsvfile)
        outputcsvwriter.writerow(("repo", "file_path", "sql_query"))

    # TODO Parallelize with the multiprocessing module. To do this, read
    # in the list of all files, then distribute the tasks among each
    # process.
    input_file_queue: multiprocessing.Queue = multiprocessing.Queue()
    """A queue to store the paths of all the input files"""

    exception_thrown: multiprocessing.synchronize.Event = multiprocessing.Event()
    """Whether an exception has been thrown in a worker."""

    files_completed: multiprocessing.sharedctypes.Synchronized[ctypes.c_ulonglong] = multiprocessing.Value(ctypes.c_ulonglong, 0)  # type: ignore[assignment]
    total_files: int = 0

    for input_file in parsedargs["input_directory"].iterdir():
        input_file_queue.put(input_file)
        total_files += 1
    
    sql_query_queue: multiprocessing.Queue = multiprocessing.Queue()
    """
    A queue to store the completed SQL queries. Will be tuples of
    (repo_name, repo_path, query)
    """

    worker_processes: list[multiprocessing.Process] = []
    for _ in range(parsedargs["process_count"]):
        worker_processes.append(multiprocessing.Process(target=worker_process,args=(
            input_file_queue, files_completed, sql_query_queue, exception_thrown
        )))

    def consume_all_from_sql_query_queue() -> None:
        """
        Consume all entries from sql_query_queue to save memory and
        prevent deadlocking.

        This function will write the consumed queries to the output
        CSV file.
        """
        with open(parsedargs["output_file"], 'a', newline="") as outputcsvfile:
            outputcsvwriter = csv.writer(outputcsvfile)
            while True:
                try:
                    sql_query_row = sql_query_queue.get(timeout=1/1048576)
                    outputcsvwriter.writerow(sql_query_row)
                except queue.Empty:
                    break
                except Exception as e:
                    # Some characters (usually foreign language characters in usernames or repo names) throw an error when trying to be written to file.
                    print(sql_query_row)
                    print (e)
    
    # Start all the subprocesses
    for process in worker_processes:
        process.start()

    last_progress_update_time: float = time.time()
    """The last time we offered the user a progress update"""
    signal_handler = SignalHandler()

    while not signal_handler.stop_requested:
        # Check if any processes are alive
        all_processes_exited: bool = True
        for process in worker_processes:
            if process.is_alive():
                all_processes_exited = False
                break
        if all_processes_exited:
            # We should exit as well
            break

        if exception_thrown.is_set():
            print("ERROR: A worker has thrown an exception. Shutting down...")
            break

        if time.time() - last_progress_update_time >= 20:
            # It's been 20 seconds. Let's give the user an update
            consume_all_from_sql_query_queue()
            print("Progress: " + str(files_completed.value) + "/" + str(total_files) + " - " + 
                  str(round(100 * int(files_completed.value) / total_files, 2)) + "%")
            last_progress_update_time = time.time()

        time.sleep(0.5)

    consume_all_from_sql_query_queue()

    unexpected_exit: bool = False
    """If true, something unexpected caused the process to exit"""
    for process in worker_processes:
        if process.is_alive():
            # In normal circumstances, this code should only be
            # reached if all proceses have exited.
            process.terminate()
            unexpected_exit = True
    
    if unexpected_exit:
        print("Something unexpected caused the program to exit.")
        print("The processing has not been completed.")
        return 1
    else:
        print("Processing complete.")
        return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))

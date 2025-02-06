# SQL Query Extractor
Extracts SQL queries from the source code of various programs. Specifically tuned to avoid false positives as much as possible.

## Prerequisities
 - Python 3.9+

## Usage
Here's an example of how to run the command:
```
python3 extractqueries.py --process-count <NUMBER OF PROCESSES> <INPUT DIRECTORY> <OUTPUT CSV FILE>
```
You can always run
```
python3 extractqueries.py -h
```
for more information and more options. 

## Supported languages
 - [x] Python

## Methodology
This project is comprised of three parts:
1. A *controller* which identifies the programming language fed in. It also handles outputting in a format that is ingestible by automated tools.
2. An *extractor* which extracts strings from the source code of programs in a specific language. It statically analyzes program syntax for strings.
3. An *parser* which parses the strings using the SQL context-free grammar to see whether they are valid SQL. The ANSI SQL standard will be followed in this case. SQL extensions that are specific to certain flavors (PostgreSQL, Oracle SQL, etc.) are not supported.

## License
```
    Copyright (C) 2025  Yuliang Huang <https://github.com/yhuang3-uf>

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; version 3.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>.
```

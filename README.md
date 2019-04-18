# tpparser
Tool to parse SOP data

## Installation

Use the pip installation manger to directly install the package from Github:

```
pip install git+https://github.com/BodenmillerGroup/tpparser.git
```

## Usage

```
tpparser -i "/input/test.md" -o "/output/test.csv" -f csv
```

| Arguments      | Description |
|----------------|-------------|
| -i, --input    | Input .md file name |
| -o, --output   | Output file name |
| -f, --format   | Output format: json (default) or csv |

import argparse
import csv
import json
import os
import re
import sys
from collections import defaultdict

# blocks which can contain sub-blocks, used mostly by parse_blocks()
# extract_filenames() also uses this to find and return files (i.e., sub-blocks of process blocks)

PROCESS_BLOCKS = ['Analysis', 'Quality control']


class ParseException(Exception):
    """Raised when an error occurs while parsing an SOP file.

    The message details why the exception occurred. More fine-grained reporting,
    e.g. source line numbers, may be added in the future if requested.
    """


def format_history(hist_line):
    """Given a semicolon-delimited version history line, splits it into up to three
    parts and returns it as a {version, date, description} dictionary.

    :param hist_line: the line of version history, e.g. "- 1.0;2018-10-30;added analysis quality control"
    :return: a dict of the form {version, date, description}
    """
    parts = hist_line.strip('- ').split(';', 3)

    if len(parts) != 3:
        raise ParseException("expected 3 version history parts, but got %d (text: \"%s\")" % (len(parts), hist_line))

    return dict(zip(['version', 'date', 'description'], parts))


def parse_block(block_str):
    lines = [x for x in re.split(r'\r?\n', block_str) if x.strip() != '']

    # ensure the header matches the expected format
    m = re.match(r'^# (?P<type>[^:]+):(?P<name>.*)$', lines[0])
    if not m:
        raise ParseException("Header line '%s' did not match expected format '# <type>: <name>'" % lines[0])
    header_parts = m.groupdict()
    block_type = header_parts['type'].strip()
    block_name = header_parts['name'].strip()

    if block_type in ['Introduction', 'Literature']:
        # these special blocks consist of free-form text after the header
        # TODO: should we generate a warning if they specify a name in the header line, since it's discarded?
        return {
            'type': block_type,
            'text': os.linesep.join(lines[1:])
        }

    elif block_type in PROCESS_BLOCKS:
        # these blocks consist of a main list of attributes, and then lists of attributes
        # in each subsection, if subsections are included.
        attributes = defaultdict(str)
        subsections = []

        # keeps track of the subsection, since the attributes that follow it belong to it
        cur_subsec = None
        # keeps track of the attribute for cases in which the attribute's value spans multiple lines
        cur_attr = None

        for line in lines[1:]:
            if line.startswith('- '):
                key, val = line.split(':', 1)
                key = key[2:].strip()  # normalize the key, e.g. by removing the '- ' prefix

                # if we're not in a subsection, set this in the block's attributes list
                # otherwise, set it in the subsection's
                target = cur_subsec['attributes'] if cur_subsec else attributes
                # we also need to keep track of this attribute in case it spans multiple lines
                cur_key = key

                target[key] = val.strip()

            elif line.startswith("## "):
                # ignore blocks describing files marked as "Not uploaded"
                if not line.startswith("## Not uploaded:"):
                    cur_subsec = {
                        'name': line[3:].strip(),
                        'attributes': defaultdict(str)
                    }
                    subsections.append(cur_subsec)

            else:
                if target and cur_key:
                    # if we encounter unqualified lines, they belong to a previously-declared attribute,
                    # in which case we concatenate them to it.
                    # if there's already a value for that attribute, we need to concatenate the new piece onto a new line;
                    # otherwise, we can skip the newline and just add the value as-is.
                    target[cur_key] += (os.linesep if target[cur_key] != '' else '') + line.strip()
                else:
                    raise ParseException(
                        "In \"%s: %s\", encounted unparseable line: %s" % (block_type, block_name, line))

        # verify that the subsection's filename conforms to what filenames should display
        for subsec in subsections:
            if 'Type' in subsec['attributes'] and subsec['attributes']['Type'] == 'file list' and \
                    not re.match(r'.*_files.txt$', subsec['name']):
                raise ParseException(
                    "In \"%s: %s\", encountered entry with type 'file list' and expected the file to end in '_files.txt', but found '%s' instead" % (
                        block_type, block_name, subsec['name']
                    )
                )
        return {
            'type': block_type,
            'name': block_name,
            'attributes': attributes,
            'items': subsections
        }

    elif block_type == 'History':
        # history blocks consist of a list of semicolon-delimited release descriptions.
        # TODO: should we generate a warning if they specify a name in the header line, since it's discarded?
        try:
            return {
                'type': block_type,
                'items': [
                    format_history(x) for x in lines[1:]
                ]
            }
        except ParseException as ex:
            raise ParseException("In \"%s\" block, %s" % (block_type, ex))

    else:
        raise ParseException("Encountered unrecognized block type '%s'" % block_type)


def parse_sop(fp=None, filename=None):
    """
    Given an SOP input, produces a parsed structure, or raises ParseException
    if errors are found.

    :param fp: a file pointer managed by the caller
    :param filename: the path to a file to parse
    :return: a structure like {meta: {}, blocks: []} containing the information
    parsed from the SOP.
    """
    if fp and not filename:
        fulltext = fp.read()
    elif filename and fp:
        with open(filename, "r") as fp:
            fulltext = fp.read()
    else:
        raise ValueError("Either fp or filename must be specified, but not both")

    # strip out comments; note that comments can't be nested within each other.
    # (the '.*?'' is a non-greedy match, meaning it'll remove the minimum
    # matching pattern, instead of the maximum match by default.
    # this allows us to have multiple comments in the file, but at the cost of
    # reduced efficiency.)
    fulltext = re.sub(r'<!--.*?-->', '', fulltext, flags=re.S)

    # blocks are delimited by at least one blank line.
    # line endings can vary depending on the platform that generated the file,
    # so we leniently split on at least \n\n, but with optional intervening \r's
    # (looking at you, Windows...)
    blocks = [x for x in re.split(r'(\r?\n)(\r?\n)+', fulltext) if x.strip() != '']

    # parse the preamble, e.g. the title, version, date, etc.
    preamble = dict(
        (bit.strip('# ') for bit in line.split(':', 1))
        for line in re.split(r'\r?\n', blocks[0])
    )

    return {
        'meta': preamble,
        'blocks': [parse_block(block_str) for block_str in blocks[1:]]
    }


def extract_filenames(fp=None, filename=None):
    """
    Given either a file pointer or filename for an SOP file, scan the file's contents
    for file references and yield each one that's found.

    :param fp: a file pointer managed by the caller
    :param filename: the path to a file to parse
    :return: a generator of {'name': <filename>, 'location': <Location attribute>|'.'} items
    """

    sop_struct = parse_sop(fp, filename)

    for block in sop_struct['blocks']:
        if block['type'] in PROCESS_BLOCKS:
            for subsec in block['items']:
                yield {
                    'name': subsec['name'],
                    'location': subsec['attributes'].get('Location', '.'),
                    'format': subsec['attributes'].get('Format', ''),
                }


def main():
    parser = argparse.ArgumentParser(description='Parsing of SOP data.')
    parser.add_argument('-i', '--input', help='Input .MD filename', type=str)
    parser.add_argument('-o', '--output', help='Output filename', type=str)
    parser.add_argument('-f', '--format', help='Format: json or csv', type=str, default='json')

    args = parser.parse_args()

    if args.input is not None:
        with open(args.input, 'r') as fi:
            result = list(extract_filenames(fp=fi))
            if args.output:
                if args.format == 'json':
                    with open(args.output, 'w') as fo:
                        json.dump(result, fo, indent=4)
                else:
                    with open(args.output, 'w') as fo:
                        writer = csv.DictWriter(fo, fieldnames=['name', 'location', 'format'])
                        writer.writeheader()
                        for row in result:
                            writer.writerow(row)
            else:
                for i in result:
                    print(i)
    else:
        raise Exception("Please specify input SOP file in .md format.")

    print("Done.")


if __name__ == '__main__':
    sys.exit(main())

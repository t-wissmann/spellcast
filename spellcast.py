#!/usr/bin/env python3

"""
spellcast - spell_ing c_heck a_nd s_tylish t_opping

spellcast aims to be a wrapper around spell checkers like aspell
to check texts with a compiler styled command-line user interface.
"""

import sys
# import os
import re
import textwrap
import argparse
import subprocess
import json
import bisect

## General comments on backends:
## A backend function should return multiple objects via 'yield'.
## Each object must be one 'mistake' and should have the following fields:
##   - 'word' a string containing the wrong word
##   - 'line' the line in the input file
##   - 'offset' the position of the word in the line
##   - 'suggestions' a list of strings containing suggestions

## Backend: Aspell
def parse_aspell_line_with_suggestions(line):
    """parse a &-line of aspell, including the &-prefix

    & WRONGWORD SUGGESTION_COUNT WORD_OFFSET_IN_LINE: SUGESSTIONS, ...
    """
    metadata = line.split(':')[0].split(' ')
    return {
        'word': metadata[1],
        'offset': int(metadata[3]) - 1, # subtract one for the prefixing '^'
        'suggestions': line.split(': ')[1].split(', ')
    }

def parse_aspell_line_no_suggestion(line):
    """parse a #-line of aspell, including the #-prefix

    & WRONGWORD WORD_OFFSET_IN_LINE
    """
    metadata = line.split(' ')
    return {
        'word': metadata[1],
        'offset': int(metadata[2]) - 1, # subtract one for the prefixing '^'
        'suggestions': []
    }


def aspell_report_file(lines, aspell_options):
    """
    Given the lines of a file, return a dict with spell checking
    results and suggestions
    """
    # see http://aspell.net/man-html/Through-A-Pipe.html
    aspell_full_command = ['aspell', '-a'] + aspell_options
    #print(aspell_full_command)
    proc = subprocess.Popen(aspell_full_command,
                            stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE,
                            text=True)

    out, _ = proc.communicate(input='\n'.join(['^' + l for l in lines]))
    aspell_lines = out.splitlines()
    line_number = 0
    for aspell_report in aspell_lines:
        if aspell_report == '':
            line_number += 1
            continue
        if aspell_report[0] in ('*', '@'):
            continue
        if aspell_report[0] == '+':
            # TODO: what to do here?
            continue
        if aspell_report[0] == '#':
            mistake = parse_aspell_line_no_suggestion(aspell_report)
            mistake['line'] = line_number
            yield mistake
        if aspell_report[0] == '&':
            mistake = parse_aspell_line_with_suggestions(aspell_report)
            mistake['line'] = line_number
            yield mistake


## Backend: Languagetool
def languagetool_report_file(lines, languagetool_options):
    """
    Given the lines of a file, return a dict with spell checking
    results and suggestions
    """
    # the accumulated line lengths. for each line, the number of characters before
    total_line_len = 0
    acc_line_lengths = []
    for l in lines:
        acc_line_lengths.append(total_line_len)
        total_line_len += len(l) + len('\n')
    acc_line_lengths.append(total_line_len)

    # run language tool
    full_input_buf = '\n'.join(lines)
    lt_full_command = ['languagetool', '--json', '-c', 'utf-8'] + languagetool_options
    proc = subprocess.Popen(lt_full_command,
                            stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE,
                            text=True)
    out, _ = proc.communicate(input=full_input_buf)

    # in older versions of languagetool:
    discard_lt_output_until_first_empty_line = False
    if discard_lt_output_until_first_empty_line:
        # discard everything in stdout until the first empty line:
        json_lines = []
        empty_line_found = False
        for line in out.splitlines():
            if empty_line_found:
                json_lines.append(line)
            else:
                if line == '':
                    empty_line_found = True
        # overwrite 'out' again
        out = '\n'.join(json_lines)
    lt_result = json.loads(out)
    print(f'number of matches = {len(lt_result["matches"])}')
    for m in lt_result['matches']:
        offset = m['offset']
        length = m['length']
        line = bisect.bisect_left(acc_line_lengths, offset),
        # the returned value is something like (1,)
        line = line[0]
        mistake = {
          'line': line - 1,
          'offset': offset - acc_line_lengths[line - 1],
          'word': full_input_buf[offset : offset + length],
          'suggestions': [],
        }
        # print(mistake)
        yield mistake


def strip_color_escapes(string):
    """strip all color escape sequences from the given string"""
    return re.sub('\033\\[[^m]*m', '', string)


def pretty_print_mistake(lines, mistake, filename):
    """Print the given spelling mistake dict, given the filename
    and all the lines of the file.
    """
    prefix = '\033[32m{}\033[36m:\033[33m{}\033[36m:\033[0m' \
             .format(filename, mistake['line'])
    indent = len(strip_color_escapes(prefix)) + mistake['offset']
    l = lines[mistake['line']]
    print(prefix + l[0:mistake['offset']] +
          '\033[1;31m' +
          l[mistake['offset']:mistake['offset'] + len(mistake['word'])] +
          '\033[0m' + l[mistake['offset'] + len(mistake['word']):])
    print(' ' * indent + '\033[1;31m' + '~' * len(mistake['word']) + '\033[0m')

    if not mistake['suggestions']:
        return
    sugg_width = 80
    sugg_prefix = '  Suggestions: '
    sugg_cur_width = len(sugg_prefix)
    is_first = True
    print(sugg_prefix, end='')
    for s in mistake['suggestions']:
        if sugg_cur_width + 2 + len(s) > sugg_width and not is_first:
            print(',\n' + ' ' * len(sugg_prefix), end='')
            sugg_cur_width = len(sugg_prefix)
        elif not is_first:
            print(', ', end='')
            sugg_cur_width += 2
        is_first = False
        print(s, end='')
        sugg_cur_width += len(s)
    print('\n')


def output_mistake_list(lines, file_name, mistakes):
    for report_item in mistakes:
        pretty_print_mistake(lines, report_item, file_name)


def output_augmented_input(lines, file_name, mistakes):
    line2mistakes = {}
    for report_item in mistakes:
        n = report_item['line']
        mistakes = line2mistakes.get(n, [])
        mistakes.append(report_item)
        line2mistakes[n] = mistakes
    for n, l in enumerate(lines):
        # if there are no mistakes in this line
        # then just print it
        if n not in line2mistakes:
            print(l)
            continue
        # if there are mistakes in this line, then highlight them
        mistakes = line2mistakes.get(n, [])
        offset2mistake = {}
        for m in mistakes:
            offset2mistake[m['offset']] = m
        output = ""
        endoffset = -1
        for offset, ch in enumerate(l + '\n'):
            if offset == endoffset:
                output += '\033[0m'
                endoffset = -1
            if offset in offset2mistake:
                mistake = offset2mistake[offset]
                endoffset = offset + len(mistake['word'])
                output += '\033[1;31m'
            output += str(ch)
        print(output, end='')


AVAILABLE_BACKENDS = {
    'aspell': aspell_report_file,
    'languagetool': languagetool_report_file,
    'lt': languagetool_report_file,
}


def check_file(file_handle, file_name, parsed_args, output_function):
    """check the given file and return the number of mistakes found"""
    lines = file_handle.readlines()
    lines = [l.rstrip('\n\r') for l in lines]
    global AVAILABLE_BACKENDS
    callback = AVAILABLE_BACKENDS[parsed_args.backend]
    mistakes = list(callback(lines, parsed_args.backendarg))
    output_function(lines, file_name, mistakes)
    return len(mistakes)


def main():
    """The main."""
    global AVAILABLE_BACKENDS
    default_backend = 'aspell'
    assert default_backend in AVAILABLE_BACKENDS
    desc = 'Non-interactive spell checking a beautified output'
    epilog = textwrap.dedent("""\
    EXAMPLE:
      - Check a pdf file
        {progname} --files some.pdf -- --lang=en_US
      - Check all tex files in the current directory with british-ize:
        {progname} --files *.tex -- -t --lang=en_GB --variety ize
      - Use an aspell wordlist:
        {progname} --files *.tex -- -t --lang=en_GB --variety ize -p ./wordlist.txt
        where wordlist.txt is a file starting with "personal_ws-1.1 en 1 "
        followed by all words in the wordlist.
    """.format(progname=sys.argv[0]))
    parser = argparse.ArgumentParser(
        description=desc,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=epilog)
    parser.add_argument('--files', metavar='FILE', type=str, nargs='+',
                        help='Files to check spelling (use stdin if this is empty). Text and PDF files are supported.')
    parser.add_argument('-b', '--backend', choices=AVAILABLE_BACKENDS.keys(),
                        default=default_backend,
                        help=f'Spell checker to use (default: {default_backend})')
    parser.add_argument('backendarg', metavar='BACKENDARG', type=str, nargs='*',
                        default=[],
                        help='Arguments passed to the aspell backend')

    parser.add_argument('--exit-code', dest='exit_code', default=False, action='store_true',
                        help='Exit code is failure is only 0 if there are not spelling mistakes')
    output_modes = {
        'augmented': output_augmented_input,
        'list': output_mistake_list,
    }
    parser.add_argument('--output-mode', dest='output_mode',
                        choices=output_modes.keys(),
                        help='Style of output', default='augmented')
    args = parser.parse_args()
    files = args.files
    count = 0
    output_function = output_modes[args.output_mode]
    if files is None or files == []:
        count += check_file(sys.stdin, '<stdin>', args, output_function)
    else:
        for filename in files:
            if re.match(r'.*\.pdf$', filename):
                pdf2text_cmd = ['pdftotext', '-layout', '-nopgbrk', filename, '-']
                pdfproc = subprocess.Popen(pdf2text_cmd, stdout=subprocess.PIPE, universal_newlines=True)
                count += check_file(pdfproc.stdout, filename, args, output_function)
                pdfproc.terminate()
                pdfproc.wait()
            else:
                with open(filename, 'r') as file_handle:
                    count += check_file(file_handle, filename, args, output_function)
    if count > 0 and args.exit_code:
        return 1
    return 0

sys.exit(main())

#!/usr/bin/env python3
import sys
import os
import subprocess

def parse_aspell_dic_miss_line(line):
    """parse a &-line of aspell, including the &-prefix

    & WRONGWORD SUGGESTION_COUNT WORD_OFFSET_IN_LINE: SUGESSTIONS, ...
    """

    metadata = line.split(':')[0].split(' ')
    res = {
        'word': metadata[1],
        'offset': int(metadata[3]) - 1, # subtract one for the prefixing '^'
        'suggestions': line.split(':')[1].split(', ')
    }
    return res

def aspell_report_file(lines, aspell_options):
    # see http://aspell.net/man-html/Through-A-Pipe.html
    aspell_full_command = ['aspell'] + aspell_options + ['-a']
    proc = subprocess.Popen(aspell_full_command,
                            stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE,
                            text=True)

    out, _ = proc.communicate(input='\n'.join([ '^' + l for l in lines]))
    aspell_lines = out.splitlines()
    line_number = 0
    for aspell_report in aspell_lines:
        if aspell_report == '':
            line_number += 1
            continue
        if aspell_report[0] in ('*', '@'):
            continue
        mistake = parse_aspell_dic_miss_line(aspell_report)
        mistake['line'] = line_number
        yield mistake

def pretty_print_mistake(lines, mistake, filename):
    prefix = '{}:{}:'.format(filename, mistake['line'])
    indent =  len(prefix) + mistake['offset']
    print(prefix + lines[mistake['line']])
    print(' ' * indent + '~' * len(mistake['word']))
    print('  Suggestions: {}'.format(', '.join(mistake['suggestions'])))
    print('')

def main(args):
    file_path = sys.argv[1]
    with open(file_path, 'r') as f:
        lines = f.readlines()
        lines = [l.rstrip('\n\r') for l in lines]
        for f in aspell_report_file(lines, ['-t', '--lang=en_GB-ize']):
            print(f)
            pretty_print_mistake(lines, f, file_path)

sys.exit(main(sys.argv))

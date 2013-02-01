############################################################
#
# parse_plays.py
#
# 

import sys
import re
import string
from collections import deque
from parser_types import ParseError, PlayDescription, PlaySegment
import parse_states

#main parser, FSM, and parsing routines

_DEBUG_LEVEL = 0

_keywords = set(['touchdown', 'safety', 'touchback',
                 'fumble', 'fumbles', 'muffs', 'recovered',
                 'intercepted', 'aborted',
                 'challenged', 'upheld', 'reversed',
                 'end', 'zone', 'team'])

_play_attributes = ['type', 'primary_name', 'yardage', 'end_yardline',
                    'pass_target', 'pass_complete', 
                    'penalty_team', 'penalty_player', 'penalty_description',
                    'penalty_accepted', 'penalty_yards', 'penalty_yardline',
                    'turnover', 'turnover_type',
                    'pass_intercepted', 'pass_interceptor',
                    'fumble_forced_by', 'fumble_yardline', 
                    'recover_team', 'recover_player', 'recover_yardline',
                    'field_goal_made', 'kick_blocked', 'returner',
                    'end_zone_result', 'attempt_type', 'attempt_success',
                    'reversed', 'noplay', 'done', 'notes']

def lex_play(playstr):
    """
    Return a list of tokens with appropriate filtering 
    from the supplied playstr.
    """
    # remove punctuation with no semantic meaning
    filterchars = '!+/"'
    punctuation = '-.():{}'
    outchars = []
    for c in playstr:
        if c in filterchars:
            continue
        elif c in punctuation:
            outchars.extend([' ', c, ' '])
        else:
            outchars.append(c)
    outstr = ''.join(outchars)
    # filter any &#xxx; character weirdness if it appears
    outstr = re.sub(r'&#\d+;', '', outstr)
    return deque(t.lower() if t.lower() in _keywords else t
                 for t in outstr.split())

class FSM:
    def __init__(self, initial_state, context=None):
        """
        Container for a set of handlers.
        Handlers correspond to states and are implemented
        as functions.
        """
        self.handlers = set()
        self.end_states = set()
        self.context = context
        self.initial_state = initial_state
        self.current_state = self.initial_state

    def reset(self):
        self.current_state = self.initial_state
        self.context = None

    def add_state(self, handler):
        self.handlers.add(handler)

    def add_end_state(self, end_state):
        self.end_states.add(end_state)
    
    def process(self, cargo):
        if not self.end_states:
            raise RuntimeError('no ending states -- cannot process')
        if _DEBUG_LEVEL > 0:
            state_list = []
        while True:
            if _DEBUG_LEVEL > 0:
                state_list.append(self.current_state.__name__)
            try:
                next_state, cargo = self.current_state(self.context, cargo)
            except IndexError:
                err_str = 'premature end of string in {0}'.format(
                    self.current_state
                    )
                if _DEBUG_LEVEL > 0:
                    print 'STATE TRACE:'
                    print '\n'.join(map(lambda s: '\t' + s,state_list))
                raise ParseError(err_str)
            if next_state in self.end_states:
                if _DEBUG_LEVEL > 2:
                    print 'PARSE OK - STATE TRACE:'
                    print '\n'.join(map(lambda s: '\t' + s,state_list))
                break
            self.current_state = next_state

def get_play_parser():
    parser = FSM(parse_states.state_initial)
    states = [getattr(parse_states, f)
              for f in dir(parse_states) if
              re.match('^state_', f)]
    end_states = [getattr(parse_states, f)
                  for f in dir(parse_states) if
                  re.match('^state_end_', f)]
    for s in states:
        parser.add_state(s)
    for es in end_states:
        parser.add_end_state(es)
    return parser

def parse_play(play, parser, verbose=False):
    try:
        parser.reset()
        parser.context = PlayDescription()
        play_tokens = lex_play(play)
        parser.process(play_tokens)
        result = parser.context
        parser.context = None
        if _DEBUG_LEVEL > 1:
            print parser.context
            print '----------'
    except ParseError, err:
        result = PlayDescription()
        result.add_segment()
        result.current_segment.type = 'ERROR'
        result.current_segment.notes = 'EXCEPTION: {0}'.format(err)
        result.is_error = True
        if verbose:
            print err
            print '%d: unable to process: %s' % (total, p)
            print '----------'                
    return result

def parse_plays(plist, verbose=False):
    parser = get_play_parser()
    parsed = []
    success = 0
    errors = 0
    total = 0
    for p in plist:
        total += 1
        parsed.append(parse_play(p, parser))
        if not parsed[-1].is_error:
            success += 1
        else:
            errors += 1
    print '%d total, %d OK, %d errors' % (total, success, errors)
    return parsed

def parse_to_csv(plays, output_file, **kwargs):
    parsed = parse_plays(plays, **kwargs)
    with open(output_file, 'w') as ofile:
        ofile.write('play_num;segment_num;')
        ofile.write(';'.join(_play_attributes))
        ofile.write(';original_description\n')
        for i, play_parsed in enumerate(parsed):
            for nseg, pseg in enumerate(play_parsed.segments):
                # start numbers with 1, not zero
                # just a touch more human-readable
                ofile.write('%d;%d;' % (i+1, nseg+1))
                ofile.write(_segment_to_csv(pseg))
                ofile.write(';')
                ofile.write(plays[i])
                ofile.write('\n')

def _segment_to_csv(play_segment):
    return ';'.join(str(getattr(play_segment, attr)) 
                    if hasattr(play_segment, attr) 
                    else 'NA' 
                    for attr in _play_attributes) 

if __name__ == '__main__':
    pass

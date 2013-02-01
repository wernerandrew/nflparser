##################################################
#
# parse_states.py
#
# This file defines a number of functions that serve
# as states in the FSM class defined in parse_plays.py.
#
# State functions must follow the signature:
#    function(context, cargo)
# And return the tuple:
#    (next_state, cargo)
# where:
#    --> cargo is a deque of remaining tokens
#    --> context is a PlayDescription object
#        that may be mutated by the function.
#
# Normal parse states must begin with 'state_'
# Parse end states (currently only one)
# must begin with 'state_end_'.
#
##################################################

import re
import inspect
from parser_types import ParseError
from itertools import islice
from collections import deque

# Convenience functions for finding ("check") or extracting ("pop"
# frequently needed information.
# Many of the below have some contextual variablility, which they 
# explicitly handle.

# Cache some regexes for speed and clarity

_first_initial = re.compile(r'^([A-Z][a-z]{0,2})$') 
_last_name     = re.compile(r"^[A-Z][a-z']")  # note included apostrophe
_team_code     = re.compile(r'^[A-Z]{2,3}$')
_0_to_99       = re.compile(r'^\d\d?$')
_two_digits    = re.compile(r'^\d\d$')

# Most of the time, after going through the lexer,
# names follow the format:
#   [<first initial>, '.', <last name>]
# where <last name> can be multiple words (e.g., Randle El)
# or surnames connected by a hyphen.
#
# Several hundred entries fail to follow these rules.  Those exceptions
# are covered by the dict below, which maps name tokens to the
# regularized name code.

_name_exceptions = {('[]',)                       : 'UNKNOWN',
                    ('Godfrey',)                  : 'R.Godfrey',
                    ('Daryl', 'Jones')            : 'D.Jones',
                    ('Andre\'', 'Davis')          : 'A.Davis',
                    ('Kevin', 'Smith')            : 'K.Smith',
                    ('Chris', 'Long')             : 'C.Long',
                    ('Alex', 'Smith')             : 'A.Smith',
                    ('Dhani', 'Jones')            : 'D.Jones',
                    ('Bracy', 'Walker')           : 'B.Walker',
                    ('Andra', 'Davis')            : 'A.Davis',
                    ('Tank', 'Williams')          : 'T.Williams',
                    ('Mike', 'Lewis')             : 'M.Lewis',
                    ('DJ', '.', 'Davis')          : 'D.Davis',
                    ('DJ', '.', 'Williams')       : 'D.Williams',
                    ('Delanie', '.', 'Walker')    : 'D.Walker',
                    ('Travis', '.', 'Johnson')    : 'T.Johnson',
                    ('Josh', '.', 'Brown')        : 'J.Brown',
                    ('Brian', '.', 'Walker')      : 'B.Walker',
                    ('Jerome', '.', 'Carter')     : 'J.Carter',
                    ('Roy', 'E', '.', 'Williams') : 'Roy_E.Williams',
                    ('K', '.', 'von', 'Oelhoffen'): 'K.von_Oelhoffen',
                    ('B', '.', 'St', '.', 'Pierre'): 'B.St.Pierre',
                    ('J', '.', 'St', '.', 'Claire'): 'J.St.Claire'}

# One issue is that when parsing penalty strings, penalty descriptions
# (e.g. 'Defensive Offsides') and the like look a lot like the 
# continuations of last name, at least from a regex perspective.  E.g.:
#    --> 'PENALTY on PIT-A. Randle El Offensive Pass Interference [...]'
#
# So if we're in a situation where we have a last name followed by
# another capitalized word, we need a list of non-last names to check
# against.  Hence this:

_penalty_tokens = set(['Chop', 'Clipping', 'Defensive', 'Delay',
                       'Disqualification', 'Encroachment',
                       'Face', 'Fair', 'False', 'Illegal', 'Ineligible',
                       'Intentional', 'Interference', 'Invalid',
                       'Kickoff', 'Leaping', 'Leverage', 'Low',
                       'Neutral', 'Offensive', 'Offside', 'Personal', 'Player',
                       'Roughing', 'Running', 'Taunting', 'Tripping',
                       'Unnecessary', 'Unsportsmanlike'])

# Convenience functions to check for patterns

def assert_tokens_and_pop(cargo, tokens):
    """Takes a cargo deque and either a single token or list of tokens.
    For each provided token, it pops the first token off of cargo, and
    checks that the popped token matches the provided token.
    
    In case of a mismatch, raises ParseError.
    If no error, the function returns and cargo will have had the
    first len(tokens) elements removed from it."""
    if isinstance(tokens, basestring):
        tlist = [tokens]
    else:
        tlist = tokens
    for token in tlist:
        tok = cargo.popleft()
        if tok != token:
            err_str = 'received unexpected token {0}, expected {1}, in {2}'
            fun_name = inspect.stack()[1][3]
            raise ParseError(err_str.format(tok, token, fun_name))
        
def _check_basic_name(cargo):
    # Check that the next 3 tokens of cargo match the usual name case of:
    # [[Abbreviated first name], '.', [Last name]].
    # Does not modify cargo.
    # Returns True on success."""
    return (_first_initial.match(cargo[0]) and 
            cargo[1] == '.' and
            _last_name.match(cargo[2]))

def _check_name_exception(cargo):
    # Check whether the front of cargo includes a token or set of tokens
    # identified as an exception and defined in _name_exceptions.
    for k in range(1,6):
        name_key = tuple(islice(cargo, k))
        if name_key in _name_exceptions:
            return True
    return False

def check_for_name(cargo):
    # Combined _check_name_exception and _check_basic_name.
    # This order is slower, but failing to check in this order led
    # to some weird behavior in corner cases.
    # Does not modify cargo.
    return _check_name_exception(cargo) or _check_basic_name(cargo)

def check_for_team(cargo):
    # Check that the next token matches the legal pattern for a name code.
    # Does not modify cargo.
    return _team_code.match(cargo[0])

def check_team_and_name(cargo):
    # Check that the beginning of cargo matches:
    # [<TEAM CODE>, *, <NAME>]
    # Does not modify cargo.
    return (check_for_team(cargo) and
            check_for_name(list(islice(cargo, 2, None))))

def check_yardline(cargo):
    # Check that the beginning of cargo matches:
    # [<YARDLINE>].
    return (cargo[0] == '50' or # case (a): the 50 
            (_team_code.match(cargo[0]) and # case (b): non-negative yard line
             _0_to_99.match(cargo[1])) or 
            (_team_code.match(cargo[0]) and # case (c): negative yard line
             cargo[1] == '-' and _0_to_99.match(cargo[2])))

def _time_ge_1min(c):
    # Helper function to determine whether to determine whether the
    # next tokens in c are consistent with a game clock time over
    # one minute and terminated by a closed parenthesis.
    #
    # Used at the beginning of a description.
    return (_0_to_99.match(c[0]) and c[1] == ':' and
            _two_digits.match(c[2]) and c[3] == ')')

def _time_lt_1min(c):
    # Helper function to determine whether to determine whether the
    # next tokens in c are consistent with a game clock time under
    # one minute and terminated by a closed parenthesis.
    #
    # Used at the beginning of a description.
    return c[0] == ':' and _two_digits.match(c[1]) and c[2] == ')'

def check_time(cargo):
    # Combined time check for >= 1min and < 1min cases.
    return _time_ge_1min(cargo) or _time_lt_1min(cargo)

def check_null_play(cargo):
    # The following situations correspond to missing or corrupted data
    # in the description.  Returns True if cargo meets one of the
    # specified nullity conditions.
    if not ''.join(cargo):  # blank, or whitespace only?
        return True
    else:
        play_str = ' '.join(cargo)
        # in limited cases, *** play under review *** is specified.
        # no description data is available here
        if '*** play under review ***' in play_str:
            return True
        # occasionally, at the end of games, html fragments including
        # "align=center" can be found.  
        # this is meaningless.
        elif 'align=center' in play_str:
            return True
    return False

def pop_n(cargo, n):
    # Pop the next n elements from the front of cargo and 
    # return a list with those elements
    if n > 0:
        result = []
        for _ in xrange(n):
            result.append(cargo.popleft())
        return result

def pop_yardline(cargo):
    # After a yardline is found (via check_yardline),
    # call this routine to grab it.
    # Possible yardline formats:
    #    - ['50']                       --> returns 50
    #    - [<TEAM_NAME>, <NUMBER>]      --> returns (<TEAM>, <NUMBER>) 
    #    - [<TEAM_NAME>, '-', <NUMBER>] --> returns (<TEAM>, -<NUMBER>)
    if cargo[0] == '50':
        cargo.popleft()
        yardline = 50
    elif check_for_team(cargo):
        if cargo[1] != '-':
            yardline = (cargo[0], int(cargo[1]))
            pop_n(cargo, 2)
        else:
            yardline = (cargo[0], -int(cargo[2]))
            pop_n(cargo, 3)
    else:
        raise ParseError('unable to pop yardline')
    return yardline

def pop_name(cargo):
    # After passing check_for_name, this function returns
    # the found name as a string.
    # Name format is generally:
    #    '<First_Initial>.<Last_Name>'
    # where spaces in <Last_Name> are joined by underscores.
    if _check_name_exception(cargo):
        for k in range(1,6):
            name_key = tuple(islice(cargo, k))
            if name_key in _name_exceptions:
                pop_n(cargo, k)
                return _name_exceptions[name_key]
    elif _check_basic_name(cargo):
        the_name = ''.join(pop_n(cargo, 3))
        # the following is necessary to pick up hyphenates 
        # plus annoyances like Antawn Randle El or B. St. Pierre
        while (cargo and (_last_name.match(cargo[0]) or
                          cargo[0] == '-')):
            if cargo[0] in _penalty_tokens:
                break
            elif cargo[0] == '-':
                the_name += cargo.popleft()
            else:
                the_name += '_%s' % cargo.popleft()
        return the_name
    else:
        raise ParseError('attempt to pop name where no name found')

def pop_time(cargo):
    # Given that check_for_time has passed, 
    # returns a tuple (minutes, seconds) and pops the
    # appropriate tokens from cargo, including the closing
    # parentheses.
    if _time_ge_1min(cargo):
        the_time = (int(cargo[0]), int(cargo[2]))
        pop_n(cargo, 4)
    elif _time_lt_1min(cargo):
        the_time = (0, int(cargo[1]))
        pop_n(cargo, 3)
    else:
        raise ParseError('attempt to pop time where no time found')
    return the_time

def state_initial(context, cargo):
    # This is the entry point for our parser.
    context.add_segment()
    # First, check against null conditions.
    if check_null_play(cargo):
        context.current_segment.type = 'NO_DESCRIPTION'
        next_state = state_end_parse_complete        
    else:
        next_tok = cargo[0]
        if next_tok == '(':
            # Many descriptions begin with '('
            # Usually this is the time.  It can also be other
            # information (e.g., formation) which we ignore.
            cargo.popleft()
            next_state = state_acquiring_annotation
        elif next_tok == 'TWO':
            # signifies a description beginning with
            # 'TWO POINT CONVERSION ATTEMPT'.  
            # This follows its own parse rules detailed below.
            cargo.popleft()
            context.current_segment.type = '2PC_ATTEMPT'
            next_state = state_get_two_point_conversion
        elif check_for_name(cargo):
            # If we get a name right at the start, usually
            # indicates a kickoff, which can be handled by
            # usual segment parsing rules.
            next_state = state_wait_play_segment
        else:
            # Otherwise, assume the description begins with
            # extraneous junk.
            next_state = state_skip_to_period
    return (next_state, cargo)


def state_skip_to_period(context, cargo):
    # Skip to the next period in the cargo.
    # Most often called when we are skipping irrelevant information
    # at the beginning of acquiring a segment.
    while True:
        next_tok = cargo.popleft()
        if next_tok == '.':
            break
    return (state_wait_play_segment, cargo)

def state_skip_to_next_segment(context, cargo):
    # Basically just 'state_skip_to_period' with a small twist.
    # Here, if we reach end of the input, we just assume
    # that we're done.
    # This is due to some entries that lack a period at the end.
    while cargo:
        # note that we can't just stop at the next period
        # sometimes we want to skip irrelevant names, which 
        # have periods.
        # so, if we find an irrelevant name, we pop it.
        try:
            has_name = check_for_name(cargo)
        except IndexError:
            has_name = False
        if has_name:
            pop_name(cargo)
        else:
            next_tok = cargo.popleft()
            if next_tok == '.':
                next_state = state_wait_play_segment
                break
    if not cargo:
        next_state = state_end_parse_complete
    return (next_state, cargo)
            

def state_acquiring_annotation(context, cargo):
    # Check parentheticals at beginning of the play
    # At this point, first parenthesis has been popped.
    next_tok = cargo[0]
    if re.match(r'\d', next_tok):
        # If we find a digit, we've found the time.
        next_state = state_acquiring_time
    else:
        # For now, we ignore all annoatations.
        # This might be a TODO at some point later.
        next_state = state_skip_outer_annotation
    return (next_state, cargo)


def state_skip_outer_annotation(context, cargo):
    # Pops tokens and ignores until closing paren found.
    while True:
        next_tok = cargo.popleft()
        if next_tok == ')':
            next_state = state_wait_play_segment
            break
    return (next_state, cargo)


def state_acquiring_time(context, cargo):
    # Checks that beginning of context conforms to accepted
    # time format.
    # If passes, pop tokens and set time for play accordingly.
    if check_time(cargo):
        context.clockmin, context.clocksec = pop_time(cargo)
        next_state = state_wait_play_segment
    else:
        err_str = 'expected time, got nonconforming input'
        raise ParseError(err_str)
    return (next_state, cargo)


def state_wait_play_segment(context, cargo):
    # This is the starting point for most analytically interesting
    # parts of the play.
    #
    # Possible values for beginning of cargo and related actions
    # are as follows:
    #   'PENALTY'   --> current segment describes a penalty.
    #   'TWO'       --> current segment is a two point conversion
    #   'Lateral'   --> someone has received a lateral
    #   'recovered' --> recovery of muff or fumble.
    #   <NAME>      --> General beginning of play segment.
    # 
    # The end condition is that cargo is empty. 
    if not cargo:
        return (state_end_parse_complete, cargo)
    # Add new play segment if necessary
    if context.current_segment.done:
        context.add_segment()

    # Play type dispatch conditions
    if cargo[0] in ['PENALTY', 'Penalty']:
        context.current_segment.type = 'PENALTY'
        next_state = state_process_penalty
        cargo.popleft()
    elif cargo[0] == 'TWO':
        context.current_segment.type = '2PC_ATTEMPT'
        next_state = state_get_two_point_conversion
    elif cargo[0] == 'Lateral':
        next_state = state_check_for_lateral
    elif cargo[0] == 'fumbles':
        cargo.popleft()
        context.current_segment.type = 'FUMBLE'
        next_state = state_process_fumble
    elif cargo[0] == 'recovered':
        cargo.popleft()
        context.current_segment.type = 'RECOVERY'
        next_state = state_process_recovery
    elif check_for_name(cargo):
        context.current_segment.primary_name = pop_name(cargo)
        next_state = state_determine_play_type
    elif cargo[0] == '(':
        # ignore parentheticals for now
        while True:
            if cargo.popleft() == ')':
                break
        next_state = state_wait_play_segment
    else:
        next_state = state_check_for_challenge
    return (next_state, cargo)

def state_determine_play_type(context, cargo):
    # Called after we have found a name in a play.
    # For now, ignore parentheticals after the name.
    if cargo[0] == '(':
        while cargo:
            if cargo.popleft() == ')':
                break
    if cargo:
        next_tok = cargo.popleft()

        # Play segment type turns on the nature of the word that 
        # follows the initial name.  
        #
        #    'and'         --> multiple people reporting in eligible (rare).
        #    'report*'     --> single person reporting in eligible.
        #    'fumbles'     --> primary player in segment fumbled
        #    'muffs catch' --> kick returner muffed catch, process like fumble
        #    'kicks'       --> kickoff (including onside kicks)
        #    'punts'       --> successful punt, not blocked
        #    'punt'        --> blocked punt ('punt is BLOCKED')
        #    'sacked'      --> QB was sacked
        #    'pass*'       --> Pass attempt
        #    'spiked'      --> Intentional spike to stop the clock
        #    '<#> yard field goal' --> field goal attempt
        #    'extra point' --> extra point attempt
        #    'touchback' --> we call it a 'run' on first pass, though most 
        #                    likely it will be interpreted as a return.
        #    Anything else: a rushing play (or possibly a return)

        if next_tok == 'and':
            # corner case for reporting in eligible.
            if check_for_name(cargo):
                context.current_segment.primary_name += ';' + pop_name(cargo)
            else:
                raise ParseError('failed to get name of second reporting '
                                 'eligible receiver where expected')
            assert_tokens_and_pop(cargo, 'reported')
            context.current_segment.type = 'REPORT_IN'
            context.current_segment.done = True
            next_state = state_skip_to_next_segment
        elif re.match(r'^report', next_tok):
            context.current_segment.type = 'REPORT_IN'
            context.current_segment.done = True
            next_state = state_skip_to_next_segment
        elif next_tok == 'fumbles':
            context.current_segment.type = 'FUMBLE'
            next_state = state_process_fumble
        elif next_tok == 'muffs' and cargo[0] == 'catch':
            context.current_segment.type = 'FUMBLE'
            next_state = state_process_fumble            
        elif next_tok == 'kicks':
            context.current_segment.type = 'KICKOFF'
            next_state = state_process_kick
        elif next_tok == 'punts':
            # matches 'punts xx yards'
            context.current_segment.type = 'PUNT'
            next_state = state_process_kick
        elif next_tok == 'punt':
            # matches 'punt is BLOCKED'
            context.current_segment.type = 'PUNT'
            next_state = state_process_kick_block
        elif re.match(r'^sacked', next_tok):
            context.current_segment.type = 'SACK'
            next_state = state_get_end_yardage
        elif re.match(r'^pass', next_tok):
            context.current_segment.type = 'PASS'
            next_state = state_process_pass
        elif next_tok == 'spiked':
            context.current_segment.type = 'PASS'
            context.current_segment.pass_complete = False
            context.current_segment.notes = 'SPIKED'
            context.current_segment.done = True
            next_state = state_skip_to_next_segment
        elif (re.match(r'\d', next_tok) and
              cargo[0] == 'yard' and
              cargo[1] == 'field' and
              cargo[2] == 'goal'):
            context.current_segment.type = 'FG_ATTEMPT'
            context.current_segment.yardage = int(next_tok)
            pop_n(cargo, 3)
            next_state = state_process_field_goal
        elif next_tok == 'extra' and cargo[0] == 'point':
            context.current_segment.type = 'XP_ATTEMPT'
            cargo.popleft()
            next_state = state_process_field_goal
        elif next_tok == 'to':
            context.current_segment.type = 'RUN'
            # a minor hack to backtrack in case there's no rush
            # direction.
            cargo.appendleft('to')
            next_state = state_get_end_yardage
        elif next_tok.lower() == 'touchback':
            context.current_segment.type = 'RUN'
            context.current_segment.end_zone_result = 'TOUCHBACK'
            context.current_segment.done = True
            next_state = state_skip_to_next_segment
        else:
            context.current_segment.type = 'RUN'
            next_state = state_get_end_yardage
    else:
        # If cargo is empty after popping the name, set segment
        # to 'NULL' and ignore it.
        context.current_segment.reset()
        context.current_segment.type = 'NULL'
        context.current_segment.done = True
        next_state = state_skip_to_next_segment
    return (next_state, cargo)

def state_check_for_lateral(context, cargo):
    # Valid segment must match pattern
    #   Lateral to [NAME] to [YARDLINE] [...] .
    context.current_segment.type = 'NULL'
    try:
        assert_tokens_and_pop(cargo, ['Lateral', 'to'])
        if check_for_name(cargo):
            lateral_name = pop_name(cargo)
            next_tok = cargo.popleft()
            if next_tok == 'to' and check_yardline(cargo):
                context.current_segment.type = 'LATERAL'
                context.current_segment.primary_name = lateral_name
                context.current_segment.end_yardline = pop_yardline(cargo)
                context.current_segment.done = True
    except ParseError:
        pass
    return (state_skip_to_next_segment, cargo)
        
def state_get_two_point_conversion(context, cargo):
    # Two point conversions follow one of the following formats:
    #   --> "[NAME] rushes ... .", or 
    #   --> "[NAME] pass to [NAME] is (complete|incomplete) [...] ."
    # After the period that ends the attempt description, 
    # look for either "ATTEMPT SUCCEEDS" or "ATTEMPT FAILS".
    
    # Skip the initial "TWO POINT CONVERSION ATTEMPT." text.
    while cargo.popleft() != '.':
        pass

    # Check conformity with run/pass format.
    if check_for_name(cargo):
        context.current_segment.primary_name = pop_name(cargo)
    else:
        raise ParseError('expected but did not find name '
                         'in two point conversion attempt')
    next_tok = cargo.popleft()
    if next_tok == 'rushes':
        context.current_segment.attempt_type = 'RUN'
    elif next_tok == 'pass':
        context.current_segment.attempt_type = 'PASS'
        next_tok = cargo.popleft()
        if next_tok == 'to':   # do we expect a receiver?
            if not check_for_name(cargo):
                raise ParseError('expected but did not find receiver '
                                 'in two point conversion attempt')
            context.current_segment.pass_target = pop_name(cargo)
            cargo.popleft()   # skip 'is'
        next_tok = cargo.popleft()
        if next_tok == 'complete':
            context.current_segment.pass_complete = True
        elif next_tok == 'incomplete':
            context.current_segment.pass_complete = False
        else:
            raise ParseError('expected "complete" or "incomplete", '
                             'got %s' % next_tok)
    # After determining run/pass information, skip to period.
    while cargo.popleft() != '.':
        pass

    # Check for attempt success or failure
    cargo.popleft()  # pop 'ATTEMPT' -- TODO: turn these into assertions
    next_tok = cargo.popleft()
    if next_tok == 'SUCCEEDS':
        context.current_segment.attempt_success = True
    elif next_tok == 'FAILS':
        context.current_segment.attempt_success = False
    else:
        raise ParseError('expected "SUCCEEDS" or "FAILS", '
                         'got %s' % next_tok)

    # ... and we're done.
    next_state = state_skip_to_next_segment
    context.current_segment.done = True
    return (next_state, cargo)

def state_process_fumble(context, cargo):
    # This is probably the most irregular pattern to match.
    # TODO: break this into smaller pieces.
    #
    # Begins with the following format:
    #   --> FUMBLES <(<NAME|Aborted>)> [at <YARDLINE>] [touched [at <YARDLINE>]]
    # And ends with one of these
    #       [...] recovered by <TEAM>[-<NAME>] at <YARDLINE>.
    #       [...] and recovers at <YARDLINE>
    #       [...] ball ob at <YARDLINE>.
    #       [...] declared dead at <YARDLINE>.

    # First handle parenthetical.  This is either the name of who
    # forced the fumble, or an indicator that the fumble occurred 
    # off of an aborted snap.
    if cargo[0] == '(':
        cargo.popleft()
        if cargo[0] == 'aborted':
            context.current_segment.fumble_forced_by = 'ABORTED_SNAP'
            pop_n(cargo, 2)
        elif cargo[0] == 'team':
            context.current_segment.fumble_forced_by = 'TEAM'
            pop_n(cargo, 2)
        else:
            while cargo[0] != ')':
                if check_for_name(cargo):
                    the_name = pop_name(cargo)
                else:
                    raise ParseError('failed to get fumble recoverer '
                                     'where expected')
                if not hasattr(context.current_segment, 'fumble_forced_by'):
                    context.current_segment.fumble_forced_by = the_name
                else:
                    context.current_segment.fumble_forced_by += ';' + the_name
            cargo.popleft()

    # Distinguish between cases specified above 
    while True:
        next_tok = cargo.popleft()
        # ignore any 'touched at' nonsense
        if next_tok == 'touched' and cargo[0] == 'at':
            continue
        elif next_tok == 'at':
            # expect to find yardline
            if not check_yardline(cargo):
                raise ParseError('failed to get fumble yardline where expected')
            context.current_segment.fumble_yardline = pop_yardline(cargo)
            continue
        # expect to find recovery information
        elif next_tok == 'recovered':
            cargo.popleft() # skip 'by'
            if check_team_and_name(cargo):
                context.current_segment.recover_team = cargo.popleft()
                cargo.popleft() # skip hyphen
                context.current_segment.recover_player = pop_name(cargo)
            elif check_for_team(cargo):
                context.current_segment.recover_team = cargo.popleft()
                context.current_segment.recover_player = 'TEAM'
            else:
                raise ParseError('expected (team and name) or (team), got '
                                 '{0}'.format(list(cargo)[0:5]))
            assert_tokens_and_pop(cargo, 'at')
            if check_yardline(cargo):
                context.current_segment.recover_yardline = pop_yardline(cargo)
            else:
                raise ParseError('did not obtain expected recovery yardline')
            break
        elif next_tok == 'and' and cargo[0] == 'recovers':
            # "... and recovers at <YARDLINE>"
            assert_tokens_and_pop(cargo, ['recovers', 'at'])
            if not check_yardline(cargo):
                raise ParseError('did not obtain expected recovery yardline')
            context.current_segment.recover_yardline = pop_yardline(cargo)
            context.current_segment.turnover = False
            # indicate that last recovering team got ball
            context.current_segment.recover_team = 'LAST_TEAM'
            if hasattr(context.current_segment, 'primary_name'):
                recover_player = context.current_segment.primary_name
            else:
                recover_player = 'LAST_PRIMARY'
            context.current_segment.recover_player = recover_player
            break
        elif next_tok == 'ball' and cargo[0] == 'out':
            # "... ball out of bounds at <YARDLINE>"
            # "... ball out of bounds in end zone <touchback|safety>"
            assert_tokens_and_pop(cargo, ['out', 'of', 'bounds'])
            context.current_segment.turnover = False
            context.current_segment.notes = 'BALL_OB'
            next_tok = cargo.popleft()
            if next_tok == 'at':
                if not check_yardline(cargo):
                    raise ParseError('in fumble, ball out of bounds but '
                                     'no yardline specified')
                context.current_segment.end_yardline = pop_yardline(cargo)
            elif next_tok == 'in':
                assert_tokens_and_pop(cargo, ['end', 'zone'])
                next_tok = cargo.popleft()
                if next_tok == 'touchback':
                    context.current_segment.end_zone_result = 'TOUCHBACK'
                elif next_tok == 'safety':
                    context.current_segment.end_zone_result = 'SAFETY'
                else:
                    raise ParseError('fumbled out of bounds in end zone; '
                                     'expected touchback or safety, '
                                     'got %s ' % next_tok)
            break
        elif next_tok == 'declared':
            assert_tokens_and_pop(cargo, ['dead', 'at'])
            if check_yardline(cargo):
                context.current_segment.end_yardline = pop_yardline(cargo)
                context.current_segment.turnover = False
            else:
                raise ParseError('fumble play declared dead without '
                                 'ending yardline')
    context.current_segment.done = True
    next_state = state_skip_to_next_segment
    return (next_state, cargo)

def state_process_kick(context, cargo):
    # Kicks or punts follow the following format.
    # After finding the 'kicks' or 'punts' token, will
    # match the following:
    #   --> <#> yards [from <YARDLINE>] to <YARDLINE>
    # followed by one of:
    #   --> 'fair catch by <NAME>'
    #   --> 'downed by <NAME>'
    #   --> 'out of bounds'
    #   --> 'touchback'
    while True:
        if cargo[0].isdigit() and re.match('^yard', cargo[1]):
            break
        else:
            cargo.popleft()
    context.current_segment.yardage = int(cargo.popleft())
    cargo.popleft()
    while True:
        # first, make sure to skip any names
        # that appear without the appropriate 
        # magic words beforehand
        if check_for_name(cargo):
            pop_name(cargo)
            continue
        next_tok = cargo.popleft()
        if next_tok == '.':
            context.current_segment.done = True
            next_state = state_wait_play_segment
            break
        if next_tok == 'fair':
            # "... fair catch by [NAME]"
            assert_tokens_and_pop(cargo, ['catch', 'by'])
            if check_for_name(cargo):
                context.current_segment.done = True
                context.current_segment.returner = pop_name(cargo)
                next_state = state_skip_to_next_segment
                break
            else:
                raise ParseError('fair catch without returner')
        elif next_tok.lower() == 'touchback':
            context.current_segment.end_zone_result = 'TOUCHBACK'
            context.current_segment.done = True
            next_state = state_skip_to_next_segment
            break
        elif next_tok in ['downed', 'out']:
            context.current_segment.done = True
            next_state = state_skip_to_next_segment
            break
        else:
            pass  # just keep looping until there's an error
    return (next_state, cargo)


def state_process_kick_block(context, cargo):
    # after learning that a kick was blocked, look for any of:
    #    --> 'recovered by' (follows usual recovery syntax)
    #    --> 'ball out of bounds' (look for the ending yardage)
    #    --> 'declared dead in end zone' (this is a safety)
    context.current_segment.kick_blocked = True
    while True:
        # ignore any names, which will also prevent us
        # from prematurely ending the segment by triggering
        # on a rogue period.
        if check_for_name(cargo):
            pop_name(cargo)
            continue
        next_tok = cargo.popleft()
        if next_tok.lower() == 'recovered':
            # "recovered by ..."
            next_state = state_process_recovery
            break
        elif next_tok == 'ball':
            # "ball out of bounds ..."
            next_state = state_get_end_yardage
            break
        elif next_tok == 'declared':
            # "declared dead in end zone"
            context.current_segment.safety = True
            context.current_segment.done = True
            next_state = state_skip_to_next_segment
            break
        elif next_tok == '.':
            context.current_segment.done = True
            next_state = state_wait_play_segment
            break
        else:
            # just keep iterating until we find one of the above
            # or reach a premature end and generate a parse error
            pass 
    return (next_state, cargo)

def state_process_field_goal(context, cargo):
    # Follows one of the following formats:
    # "... field goal is <GOOD|NO GOOD|BLOCKED|Aborted>"
    # "... extra point is <GOOD|NO GOOD|BLOCKED|Aborted>"

    # We take over at the 'is' token:
    assert_tokens_and_pop(cargo, 'is')
    next_tok = cargo.popleft().lower()  # simplify case issues
    if next_tok == 'good':
        context.current_segment.field_goal_made = True
        context.current_segment.done = True
        next_state = state_skip_to_next_segment
    elif next_tok == 'no' and cargo[0].lower() == 'good':
        context.current_segment.field_goal_made = False
        context.current_segment.done = True
        next_state = state_skip_to_next_segment
    elif next_tok == 'blocked':
        context.current_segment.field_goal_made = False
        next_state = state_process_kick_block
    elif next_tok == 'aborted':
        context.current_segment.field_goal_made = False
        next_state = state_skip_to_next_segment
    else:
        raise ParseError('unrecognized field goal result')
    return (next_state, cargo)
    
def state_check_for_challenge(context, cargo):
    # Challenges follow one of several patterns, and present a
    # problem because they can be hard to distinguish from
    # unparseable commentary.
    #
    # Challenges will follow one of the following formats:
    #   '[...] challenged [...] and the play was <upheld|reversed>'
    #   '[...] challenged by <TEAM|"Review Assistant"> and <upheld|reversed>' 
    # Anything else is ignored.

    is_challenge = False
    while cargo:
        if cargo[0] == 'challenged':
            is_challenge = True
            break
        elif cargo[0] == '.':
            # indicates we just do a garden variety segment skip
            break
        cargo.popleft()
    if is_challenge:
        # grab the current sentence up to but not including the period
        # A valid challenge sentence ends with:
        #    '... and the play was (upheld|reversed)'
        cur_sentence_words = []
        while cargo and cargo[0] != '.':
            cur_sentence_words.append(cargo.popleft())
        cur_sentence = ' '.join(cur_sentence_words)
        # for the following test:
        # note that the second match covers a corner case early in the
        # data set.  majority of cases follow the first
        # pattern.
        #print 'SENTENCE', cur_sentence
        _challenge_pattern_1 = re.compile(
            r'.*and the play was (upheld|reversed)'
            )
        _challenge_pattern_2 = re.compile(
            r'.*by ([A-Z]{2,3}|Review Assistant) and (upheld|reversed)'
            )
        if (_challenge_pattern_1.match(cur_sentence) or
            _challenge_pattern_2.match(cur_sentence)):
            context.current_segment.type = 'CHALLENGE'
            if cur_sentence_words[-1] == 'upheld':
                context.current_segment.reversed = False
            elif cur_sentence_words[-1] == 'reversed':
                context.current_segment.reversed = True
            else:
                raise ParseError('found challenge but unable to determine '
                                 'if upheld')
        else:
            context.current_segment.type = 'NULL'
    else:
        context.current_segment.type = 'NULL'
    context.current_segment.done = True
    return (state_skip_to_next_segment, cargo)

def state_process_recovery(context, cargo):
    # Recoveries follow following format:
    #   "[...] recovered by <TEAM>-<NAME> [at <YARDLINE>]"
    
    # We take over at 'by'
    next_tok = cargo.popleft()
    if (next_tok == 'by' and
        check_team_and_name(cargo)):
        # check format of next section
        team_name = cargo.popleft()
        cargo.popleft()
        recoverer = pop_name(cargo)
        context.current_segment.recover_team = team_name
        context.current_segment.recover_player = recoverer
    else:
        # current segment is just commentary and thus null
        context.current_segment.reset()
        context.current_segment.type = 'NULL'
        context.current_segment.done = True
        return (state_skip_to_next_segment, cargo)
    next_tok = cargo.popleft()
    # note that not all recoveries have yardlines.
    # in cases of onside kicks, the yardline is implicit from
    # the kick yardage.
    if (next_tok == 'at' and check_yardline(cargo)):
        yardline = pop_yardline(cargo)
        context.current_segment.recover_yardline = yardline
    while cargo:
        next_tok = cargo.popleft()
        if next_tok == '.':
            break
    context.current_segment.done = True
    next_state = state_wait_play_segment
    return (next_state, cargo)


def state_get_end_yardage(context, cargo):
    # From this state, yardages always are preceded by 'at'
    # or 'to'.  In this state, the yardage is also the last
    # interesting thing to be found in the play segment, so 
    # we indicate that the play is done.
    try:
        while True:
            next_tok = cargo.popleft()
            if next_tok in ['at', 'to']:
                if check_yardline(cargo):
                    context.current_segment.end_yardline = pop_yardline(cargo)
                    break
            elif next_tok.lower() == 'safety':
                context.current_segment.end_yardline = 0
                context.current_segment.end_zone_result = 'SAFETY'
                break
            elif next_tok.lower() == 'touchdown':
                context.current_segment.end_yardline = 0
                context.current_segment.end_zone_result = 'TOUCHDOWN'
                break
            elif next_tok.lower() == 'touchback':
                context.current_segment.end_yardline = 0
                context.current_segment.end_zone_result = 'TOUCHBACK'
                break
    # A possible TODO: figure out the tackler, if segment type
    # is either 'RUN' or 'PASS'.

    # This is the fall through for miscellaneous string fragments,
    # especially occurring at the end of plays.
    # Because 'RUN' is the default segment type, if we get a 'run'
    # without an end yardage, we assume the segment is to be ignored.
    except IndexError:
        if context.current_segment.type == 'RUN':
            context.current_segment.type = 'NULL'
    context.current_segment.done = True
    next_state = state_skip_to_next_segment
    return (next_state, cargo)

def state_process_pass(context, cargo):
    while True:
        next_tok = cargo.popleft()
        if next_tok == 'incomplete':
            # "... pass [...] incomplete [direction] [to target] ."
            # "... pass [...] incomplete [direction]."
            context.current_segment.pass_complete = False
            context.current_segment.pass_intercepted = False
        # if next word is 'to', then we grab the name
            if cargo and cargo[0] == 'to':
                cargo.popleft()
                if check_for_name(cargo):
                    target_name = pop_name(cargo)
                    context.current_segment.pass_target = target_name
                else:
                    err_str = 'expected name of pass target, got {0}'
                    raise ParseError(err_str.format(pop_n(cargo, 3)))
            context.current_segment.done = True
            next_state = state_skip_to_next_segment
            break
        elif next_tok == 'to':
            # "... pass [...] to [target] to [yardline] [...] ."
            context.current_segment.pass_complete = True
            if check_for_name(cargo):
                context.current_segment.pass_target = pop_name(cargo)
            else:
                err_str = 'expected name of pass target, got {0}'
                raise ParseError(err_str.format(pop_n(cargo, 3)))
            next_state = state_get_end_yardage
            break
        elif next_tok == 'intended':
            # believe it or not, this always denotes an interception:
            # "... pass intended for [target] INTERCEPTED by [interceptor] 
            #  at [yardline]"
            context.current_segment.turnover = True
            context.current_segment.turnover_type = 'INTERCEPTION'
            context.current_segment.pass_intercepted = True
            next_tok = cargo.popleft()
            if next_tok == 'for' and check_for_name(cargo):
                context.current_segment.pass_target = pop_name(cargo)
            else:
                raise ParseError('expected but did not find target')
            while next_tok != 'by':
                next_tok = cargo.popleft()
            if check_for_name(cargo):
                context.current_segment.pass_interceptor = pop_name(cargo)
            else:
                raise ParseError('expected but did not find interceptor')
            next_state = state_get_end_yardage
            break
        elif next_tok == 'intercepted':
            # "... pass INTERCEPTED by [interceptor] at [yardline] ."
            next_tok == cargo.popleft()
            if next_tok == 'by' and check_for_name(cargo):
                context.current_segment.pass_interceptor = pop_name(cargo)
            next_state = state_get_end_yardage
            break
        else:
            pass
            # err_str = 'unrecognized token {0} in pass context'
            # raise ParseError(err_str.format(next_tok))
    return (next_state, cargo)


def state_process_penalty(context, cargo):
    # Follows the format:
    #   --> "penalty on <TEAM>-<NAME> <Description>"
    # followed by one of:
    #   --> "<#> yards enforced at <YARDLINE>" 
    #   --> "<#> yards enforced between downs."
    #   --> "declined"
    # We have already processed the "PENALTY" token
    # so we should see 'on':
    next_tok = cargo.popleft()
    if next_tok == 'on' and check_team_and_name(cargo):
        context.current_segment.penalty_team = cargo.popleft()
        cargo.popleft() # ditch the hyphen
        context.current_segment.penalty_player = pop_name(cargo)
    elif next_tok == 'on' and check_for_team(cargo):
        context.current_segment.penalty_team = cargo.popleft()
        context.current_segment.penalty_player = 'NA'
    else:
        # if neither of these cases hold, we're just looking
        # at a fluff sentence that happens to begin with
        # 'Penalty'.  carry on.
        context.current_segment.type = 'NULL'
        context.current_segment.done = True
        return (state_skip_to_next_segment, cargo)

    # now build penalty description by appending words
    # until we get to one of the sentinels that tells us to stop
    desc = ''
    next_tok = cargo.popleft()
    while (not (next_tok.isdigit() and re.match('^yard', cargo[0])) and
           not next_tok in ['declined', 'offsetting', 'superseded']):
        if desc:
            desc += ' '
        desc += next_tok
        next_tok = cargo.popleft()
    context.current_segment.penalty_description = desc

    # now figure out whether the penalty was accepted, declined,
    # superseded, or whether we have an offsetting penalties situation.
    if next_tok in ['declined', 'superseded']:
        context.current_segment.penalty_accepted = False
        if next_tok == 'superseded':
            context.current_segment.notes = 'SUPERSEDED'
        next_state = state_skip_to_next_segment
    elif next_tok == 'offsetting':
        context.current_segment.penalty_accepted = False
        context.current_segment.noplay = True
        context.current_segment.notes = 'OFFSET'
        next_state = state_skip_to_next_segment
    else:
        # penalty was accepted
        context.current_segment.penalty_accepted = True
        context.current_segment.penalty_yards = int(next_tok)
        # distinguish 'between downs' case and yardline
        pop_n(cargo, 2)  # skip "yards enforced"
        next_tok = cargo.popleft()
        if next_tok == 'at' and check_yardline(cargo):
            context.current_segment.penalty_yardline = pop_yardline(cargo)
        elif next_tok == 'between':
            assert_tokens_and_pop(cargo, 'downs')
            context.current_segment.notes = 'ENFORCED_BETWEEN_DOWNS'
        next_tok = cargo.popleft()
        if next_tok == '.':
            next_state = state_wait_play_segment
        elif next_tok == '-' and cargo.popleft() == 'No':
            context.current_segment.noplay = True
            next_state = state_skip_to_next_segment
        else:
            next_state = state_skip_to_next_segment
    context.current_segment.done = True
    return (next_state, cargo)

def state_end_parse_complete(context, cargo):
    # Nothing happens here, we're done.
    return None

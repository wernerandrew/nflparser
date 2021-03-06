############################################################
#
# builder.py
#
# Parses a raw NFL season file to produce a Season object.
# 
# A Season is comprised of Games, which in turn comprises
# a set of Plays, which should surprise no one.
#
############################################################

from parser_types import PlayDescription
from parser_frontend import get_play_parser, parse_play
from csv import DictReader
import copy
import numpy as np

# maps team codes used in descriptions to team codes used in
# offense/defense designations

_team_map = {'ARZ': 'ARI',
             'ATL': 'ATL',
             'BLT': 'BAL',
             'BUF': 'BUF',
             'CAR': 'CAR', 
             'CHI': 'CHI',
             'CIN': 'CIN',
             'CLV': 'CLE', 
             'DAL': 'DAL', 
             'DEN': 'DEN',
             'DET': 'DET',
             'GB' : 'GB',
             'HST': 'HOU',
             'IND': 'IND',
             'JAX': 'JAC',
             'KC' : 'KC',
             'MIA': 'MIA',
             'MIN': 'MIN',
             'NE' : 'NE',
             'NO' : 'NO',
             'NYG': 'NYG',
             'NYJ': 'NYJ',
             'OAK': 'OAK',
             'PHI': 'PHI',
             'PIT': 'PIT',
             'SD' : 'SD',
             'SEA': 'SEA',
             'SF' : 'SF',
             'SL' : 'STL',
             'TB' : 'TB',
             'TEN': 'TEN',
             'WAS': 'WAS'}

def _match_teams(team_desc, home, away):
    # name_desc = name from the description
    # home = home team from the game record
    # away = away team from the game record
    # first check for exact match
    if team_desc == home:
        return 'HOME'
    elif team_desc == away:
        return 'AWAY'
    # next do lookup of "fixed" name
    team_desc_fixed = _team_map.get(team_desc, team_desc)
    if team_desc_fixed == home:
        return 'HOME'
    elif team_desc_fixed == away:
        return 'AWAY'
    else:
        raise ParseError('unable to match team name: '
                         '%s (%s, %s)' % (team_desc, home, away))

class Season(object):
    pass

class Game(object):
    """Encapsulates information relating to a game and
    provides basic routines for adding plays.

    """
    def __init__(self, game_id=None, date=None, home=None, away=None):
        """Accepts either a game_id or three parameters: date, home, away.
        Date should be an integer in YYYYMMDD format for consistency
        with data file conventions.

        When a game_id is provided, it takes precedence over the 
        other parameters.

        """
        if game_id is not None:
            # if given a game id, parse it.
            # format: YYYYMMDD_[AWAY]@[HOME]
            date_str, teams = game_id.split('_')
            away, home = teams.split('@')
            date = int(date_str)
        self.date = date
        self.home = home
        self.away = away
        self.home_points = 0
        self.away_points = 0
        self.winner = None
        self.plays = []
        
    def add_play(self, play):
        self.home_points += play.home_points
        self.away_points += play.away_points
        self.plays.append(play)

    def finish_game(self):
        if self.home_points > self.away_points:
            self.winner = self.home
        elif self.away_points > self.home_points:
            self.winner = self.away
        else:
            self.winner = 'TIE_GAME'

class Play(object):
    """Simple data container for now.

    """
    def __init__(self):
        self.home_points = 0
        self.away_points = 0

    def __repr__(self):
        return ';'.join('{0}={1}'.format(k, v)
                        for k, v in vars(self).iteritems())

class GameFactory(object):
    """Initialized with a csv file of raw data and an instance
    of PlayMaker for assembling plays.

    The iter_games method generates an season of games.

    """
    def __init__(self, csvfile, playmaker):
        self._csvfile = csvfile
        self._playmaker = playmaker
        
    def make_games(self):
        return list(self.iter_games())

    def iter_games(self):
        with open(self._csvfile) as fhandle:
            reader = DictReader(fhandle)
            current_game_id = ''
            current_game = None
            for row in reader:
                if current_game_id != row['gameid']:
                    current_game_id = row['gameid']
                    if current_game is not None:
                        current_game.finish_game()
                        yield current_game
                    current_game = Game(game_id=row['gameid'])
                play = self._playmaker.make_play(current_game.home,
                                                 current_game.away,
                                                 row)
                current_game.add_play(play)
            if current_game is not None:
                yield current_game

        
class PlayMaker(object):
    """PlayMaker is designed to take a row dict from a
    season csv file and construct a play via the make_play method.
    
    The base PlayMaker class performs common tasks such as converting
    yardages to the 0-100 scale, obtaining down and distance information,
    etc.

    PlayMaker subclasses may very in their implementation of the 
    transform method, which takes a list of play descriptions and
    extracts the required information.  For instance, certain analyses
    may wish to focus on the alternative play possibilities under
    challenges; others may not.  Some may want to disaggregate kickoffs
    or punts from their related return; others may not.  Etc., etc.    

    Conventions:
      -- yardlines go from 0 to 100; home goal = 0, away goal = 100
      -- times count up from zero in seconds from the beginning of
         the game
      
    """
    def __init__(self):
        self._parser = get_play_parser()

    def make_play(self, home, away, row, new_game=False,
                  score_from_play=False):
        new_play = Play()
        self.home = home
        self.away = away
        self._parser.context = PlayDescription()
        try:
            new_play.down = int(row['down'])
            new_play.togo = int(row['togo'])
        except ValueError:
            new_play.down = 0
            new_play.togo = 0
        new_play.offense = row['off']
        # sometimes (rarely) this field is blank
        # however, when it is, there is an entry for defense.
        if not new_play.offense:
            print 'Repairing missing (%s @ %s)' % (away, home),
            if row['def'] == self.away:
                new_play.offense = self.home
            else:
                new_play.offense = self.away
            print 'offense = %s' % new_play.offense
        # count up seconds from zero
        if new_game:
            # minutes are often incorrectly set for first play of game
            new_play.time = 0
        else:
            try:
                min_left = int(row['min'])
                sec_left = int(row['sec'])
            except ValueError:
                min_left = -1
                sec_left = -1
            new_play.time = 60*(60 - min_left) - sec_left
        # in files, yardlines are set from perspective of offense
        # here, we 
        try:
            raw_start_yardline = int(row['ydline'])
            if new_play.offense == self.home:
                new_play.start_yardline = 100 - raw_start_yardline
                new_play.yardage_mult = 1
            else:
                new_play.start_yardline = raw_start_yardline
                new_play.yardage_mult = -1
        except ValueError:
            raw_start_yardline = np.nan
        if not score_from_play:
            try:
                offscore = int(row['offscore'])
                defscore = int(row['defscore'])
            except ValueError:
                offscore = -1
                defscore = -1
        return self.transform(new_play, row['description'])

    def transform(self, play, description):
        raise NotImplementedError()    

    def _get_yardline(self, offense, segment, yardline):
        """Some annoying logic that figures out how to interpret
        our parsed-out yardlines from the descriptions."""
        end = getattr(segment, yardline)
        if isinstance(end, tuple):
            which_team = _match_teams(end[0], self.home, self.away)
            if which_team == 'HOME':
                result = end[1]
            else:
                result = 100 - end[1]
        else:
            if end == 0:
                if offense == self.home:
                    if segment.end_zone_result in ['touchdown', 'touchback']:
                        result = 0
                    else:
                        result = 100
                else:
                    if segment.end_zone_result in ['touchdown', 'touchback']:
                        result = 100
                    else:
                        result = 0
            else:
                result = end
        return result

class BasicPlayMaker(PlayMaker):
    """
    Captures only run or passing plays with a single non-null segment.
    Filters out turnovers, challenges, penalties, or 
    really anything interesting at all.

    """
    def transform(self, play, description):
        parsed = parse_play(description, self._parser)
        new_play = copy.deepcopy(play)
        if parsed.is_error:
            new_play.type = 'NA'
        else:
            seg = [s for s in parsed.segments if s.type != 'NULL']
            if len(seg) == 1:
                segment = seg[0]
                new_play.type = segment.type
                # default to no gain
                end = new_play.start_yardline
                if hasattr(segment, 'end_zone_result'):
                    new_play.end_zone_result = segment.end_zone_result
                else:
                    new_play.end_zone_result = 'NA'
                if new_play.type == 'RUN':
                    end = self._get_yardline(
                        new_play.offense, segment, 'end_yardline'
                        )
                    # deal with ambiguity with ending yardline
                elif (new_play.type == 'PASS' and 
                      hasattr(segment, 'pass_complete') and 
                      segment.pass_complete):
                    end = self._get_yardline(
                        new_play.offense, segment, 'end_yardline'
                        )
                else:
                    new_play.type = 'NA'
                new_play.yards = end - new_play.start_yardline
            else:
                new_play.type = 'NA'
        return new_play


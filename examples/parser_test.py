import sys
sys.path.append('..')
import random
from nflparser import parse_plays, GameFactory, BasicPlayMaker

def example_parse():
    """Demonstrates the use of the parse_plays function
    to read and process a play description."""
    print 'example_parse()'
    with open('test_descriptions.txt') as fsock:
        plays = fsock.read().split('\n')
    random.shuffle(plays)
    parsed = parse_plays(plays[:5])
    for i, p in enumerate(parsed):
        print '-------------'
        print 'Play %d:' % (i + 1)
        print 'Original:', plays[i]
        for j, seg in enumerate(p.segments):
            print 'Parsed segment %d:' % (j + 1),
            print str(seg)

def example_build():
    """Demonstrates the use of the GameFactory and
    PlayMaker classes to process an entire game."""
    factory = GameFactory('test_games.csv', BasicPlayMaker())
    games = factory.make_games()
    print 'example_build()'
    print 'Parsed %d games.' % len(games)
    for g in games:
        print '-------------'
        print '%d: %s at %s' % (g.date, g.away, g.home)
        print '%d plays total' % len(g.plays)

if __name__ == '__main__':
    example_parse()
    print '--------------------'
    print '--------------------'
    example_build()

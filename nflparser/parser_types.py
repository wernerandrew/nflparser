#parser types definition file

class ParseError(Exception):
    pass

class PlayDescription(object):
    def __init__(self):
        self.reset()

    def __str__(self):
        return '\n'.join(map(str, self.segments))

    def __repr__(self):
        return str(self)

    def reset(self):
        self.segments = []
        self.is_error = False
        
    def add_segment(self):
        self.segments.append(PlaySegment())

    @property
    def current_segment(self):
        return self.segments[-1]

class PlaySegment(object):
    def __init__(self):
        self.reset()

    def reset(self):
        self.type = None
        self.done = False
        self.turnover = False
        self.noplay = False

    def __str__(self):
        return ';'.join('{0}={1}'.format(k,v) 
                        for k,v in self.__dict__.iteritems())

    def __repr__(self):
        return str(self)

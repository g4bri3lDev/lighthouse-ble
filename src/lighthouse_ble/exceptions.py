"""Errors raised by lighthouse-ble. Callers only ever see these, never raw bleak errors."""


class LighthouseError(Exception):
    """Base class for all lighthouse-ble errors."""


class LighthouseConnectionError(LighthouseError):
    """Connecting or talking to a base station failed."""


class UnsupportedError(LighthouseError):
    """The base station (or its firmware) cannot do this."""


class InvalidChannelError(LighthouseError, ValueError):
    """A V2 channel outside 1-16."""


class MissingV1IdError(LighthouseError):
    """A V1 command needs the station ID printed on the back label."""


class InvalidV1IdError(LighthouseError, ValueError):
    """A V1 station ID that is not 8 (or 4 completable) hex digits."""

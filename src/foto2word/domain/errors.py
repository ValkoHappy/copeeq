class Foto2WordError(Exception):
    """Base class for expected, user-reportable failures."""


class ProfileNotFoundError(Foto2WordError):
    pass


class InvalidImageError(Foto2WordError):
    pass


class VisionModelError(Foto2WordError):
    """The vision model failed, refused or returned an unusable answer."""


class InvalidProfileError(Foto2WordError):
    pass

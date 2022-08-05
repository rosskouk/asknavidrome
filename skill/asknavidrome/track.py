class Track:
    """An object that represents an audio track
    """

    def __init__(self,
                 id: str = '', title: str = '', artist: str = '', artist_id: str = '',
                 album: str = '', album_id: str = '', track_no: int = 0, year: int = 0,
                 genre: str = '', duration: int = 0, bitrate: int = 0, uri: str = '',
                 offset: int = 0, previous_id: str = '') -> None:
        """
        :param str id: The song ID. Defaults to ''
        :param str title: The song title. Defaults to ''
        :param str artist: The artist name. Defaults to ''
        :param str artist_id: The artist ID. Defaults to ''
        :param str album: The album name. Defaults to ''
        :param str album_id: The album ID. Defaults to ''
        :param int track_no:  The track number. Defaults to 0
        :param int year: The release year. Defaults to 0
        :param str genre: The music genre. Defaults to ''
        :param int duration: The length of the track in seconds. Defaults to 0
        :param int bitrate: The bit rate in kbps. Defaults to 0
        :param str uri: The song's URI for streaming. Defaults to ''
        :param int offset: The position in the track to start playback in milliseconds. Defaults to 0
        :param str previous_id: The ID of the previous song in the playlist. Defaults to ''
        :return: None
        """

        self.id: str = id
        self.artist: str = artist
        self.artist_id: str = artist_id
        self.title: str = title
        self.album: str = album
        self.album_id: str = album_id
        self.track_no: int = track_no
        self.year: int = year
        self.genre: str = genre
        self.duration: int = duration
        self.bitrate: int = bitrate
        self.uri: str = uri
        self.offset: int = offset
        self.previous_id: str = previous_id

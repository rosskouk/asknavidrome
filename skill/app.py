from datetime import datetime
from flask import Flask, render_template
import logging
from multiprocessing import Process
from multiprocessing.managers import BaseManager
import os
import random
import sys

from ask_sdk_core.skill_builder import SkillBuilder
from ask_sdk_core.dispatch_components import AbstractRequestHandler, AbstractRequestInterceptor, AbstractResponseInterceptor
from ask_sdk_core.utils import is_request_type, is_intent_name, get_slot_value_v2, get_intent_name, get_request_type
from ask_sdk_core.handler_input import HandlerInput
from ask_sdk_model import Response
from ask_sdk_core.dispatch_components import AbstractExceptionHandler
from flask_ask_sdk.skill_adapter import SkillAdapter

import asknavidrome.subsonic_api as api
import asknavidrome.media_queue as queue
import asknavidrome.controller as controller
from asknavidrome.fuzzy_match import CatalogCache, fuzzy_find_album, fuzzy_find_genre

# Create web service
app = Flask(__name__)

# ProxyFix to make internal HTTP look like HTTPS
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# Create skill object
sb = SkillBuilder()

# Setup Logging
logger = logging.getLogger()  # Create logger
level = logging.getLevelName('DEBUG')
logger.setLevel(level)  # Set logger log level

log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

handler = logging.StreamHandler(sys.stdout)
handler.setLevel(level)
handler.setFormatter(log_formatter)

logger.addHandler(handler)

#
# Get service configuration
#

logger.info('AskNavidrome 0.10!')
logger.debug('Getting configuration from the environment...')


def require_env(name: str, log_value: bool = True) -> str:
    """Fetch a required environment variable or raise NameError."""

    value = os.getenv(name)
    if value is None:
        logger.error(f'{name} was not found!')
        raise NameError(f'{name} is required')
    if log_value:
        logger.info(f'{name} is set to: {value}')
    else:
        logger.info(f'{name} is set')
    return value


sb.skill_id = require_env('NAVI_SKILL_ID')
min_song_count = require_env('NAVI_SONG_COUNT')
navidrome_url = require_env('NAVI_URL')
navidrome_user = require_env('NAVI_USER')
navidrome_passwd = require_env('NAVI_PASS', log_value=False)
navidrome_port = require_env('NAVI_PORT')
navidrome_api_location = require_env('NAVI_API_PATH')
navidrome_api_version = require_env('NAVI_API_VER')

logger.debug('Configuration has been successfully loaded')

# Set log level based on config value
if 'NAVI_DEBUG' in os.environ:
    navidrome_log_level = int(os.getenv('NAVI_DEBUG'))

    if navidrome_log_level == 0:
        # Warnings and higher
        logger.setLevel(logging.WARNING)
        logger.warning('Log level set to WARNING')

    elif navidrome_log_level == 1:
        # Info messages and higher
        logger.setLevel(logging.INFO)
        logger.info('Log level set to INFO')

    elif navidrome_log_level == 2:
        # Debug with request and response interceptors
        logger.setLevel(logging.DEBUG)
        logger.debug('Log level set to DEBUG')

    elif navidrome_log_level == 3:
        # Debug with request / response interceptors and Web GUI
        logger.setLevel(logging.DEBUG)
        logger.debug('Log level set to DEBUG')

    else:
        # Invalid value provided - set to WARNING
        navidrome_log_level = 0
        logger.setLevel(logging.WARNING)
        logger.warning('Log level set to WARNING')

# Create a shareable queue than can be updated by multiple threads to enable larger playlists
# to be returned in the back ground avoiding the Amazon 8 second timeout
BaseManager.register('MediaQueue', queue.MediaQueue)
manager = BaseManager()
manager.start()
play_queue = manager.MediaQueue()
logger.debug('MediaQueue object created...')

# Variable to store the additional thread used to populate large playlists
# this is used to avoid concurrency issues if there is an attempt to load multiple playlists
# at the same time.
backgroundProcess = None

# Connect to Navidrome
connection = api.SubsonicConnection(navidrome_url,
                                    navidrome_user,
                                    navidrome_passwd,
                                    navidrome_port,
                                    navidrome_api_location,
                                    navidrome_api_version)

try:
    connection.ping()

except Exception:
    raise RuntimeError('Could not connect to SubSonic API!')

# Fuzzy matching config
fuzzy_threshold = int(os.getenv('NAVI_FUZZY_THRESHOLD', '70'))
logger.info(f'Fuzzy match threshold: {fuzzy_threshold}')

catalog = CatalogCache(connection)

logger.info('AskNavidrome Web Service is ready to start!')


#
# Handler Classes
#

class LaunchRequestHandler(AbstractRequestHandler):
    """Handle LaunchRequest and NavigateHomeIntent"""

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return (
            is_request_type('LaunchRequest')(handler_input) or
            is_intent_name('AMAZON.NavigateHomeIntent')(handler_input)
        )

    def handle(self, handler_input: HandlerInput) -> Response:
        logger.debug('In LaunchRequestHandler')

        connection.ping()
        speech = sanitise_speech_output('Ready!')

        handler_input.response_builder.speak(speech).ask(speech)
        return handler_input.response_builder.response


class CheckAudioInterfaceHandler(AbstractRequestHandler):
    """Check if device supports audio play.

    This can be used as the first handler to be checked, before invoking
    other handlers, thus making the skill respond to unsupported devices
    without doing much processing.
    """

    def can_handle(self, handler_input: HandlerInput) -> bool:
        if handler_input.request_envelope.context.system.device:
            # Since skill events won't have device information
            return handler_input.request_envelope.context.system.device.supported_interfaces.audio_player is None
        else:
            return False

    def handle(self, handler_input: HandlerInput) -> Response:
        logger.debug('In CheckAudioInterfaceHandler')

        _ = handler_input.attributes_manager.request_attributes['_']
        handler_input.response_builder.speak('This device is not supported').set_should_end_session(True)

        return handler_input.response_builder.response


class SkillEventHandler(AbstractRequestHandler):
    """Close session for skill events or when session ends.

    Handler to handle session end or skill events (SkillEnabled,
    SkillDisabled etc.)
    """

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return (handler_input.request_envelope.request.object_type.startswith(
                'AlexaSkillEvent') or
                is_request_type('SessionEndedRequest')(handler_input))

    def handle(self, handler_input: HandlerInput) -> Response:
        logger.debug('In SkillEventHandler')

        return handler_input.response_builder.response


class HelpHandler(AbstractRequestHandler):
    """Handle HelpIntent"""

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name('AMAZON.HelpIntent')(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        logger.debug('In HelpHandler')

        text = sanitise_speech_output('AskNavidrome lets you interact with media servers that offer a Subsonic compatible A.P.I.')
        handler_input.response_builder.speak(text)

        return handler_input.response_builder.response


class NaviSonicPlayMusicByArtist(AbstractRequestHandler):
    """Handle NaviSonicPlayMusicByArtist

    Play a selection of songs for the given artist
    """

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name('NaviSonicPlayMusicByArtist')(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        global backgroundProcess
        logger.debug('In NaviSonicPlayMusicByArtist')

        # Check if a background process is already running, if it is then terminate the process
        # in favour of the new process.
        if backgroundProcess is not None:
            backgroundProcess.terminate()
            backgroundProcess.join()

        # Get the requested artist
        artist = get_slot_value_v2(handler_input, 'artist')

        # Search for an artist
        artist_lookup = connection.search_artist_fuzzy(artist.value, catalog, fuzzy_threshold)

        if artist_lookup is None:
            text = sanitise_speech_output(f"I couldn't find the artist {artist.value} in the collection.")
            handler_input.response_builder.speak(text).ask(text)

            return handler_input.response_builder.response

        else:
            # Get a list of albums by the artist
            artist_album_lookup = connection.albums_by_artist(artist_lookup[0].get('id'))

            # Build a list of songs to play
            song_id_list = connection.build_song_list_from_albums(artist_album_lookup, min_song_count)
            play_queue.clear()

            controller.enqueue_songs(connection, play_queue, song_id_list[:2])
            if song_id_list[2:]:
                backgroundProcess = Process(target=queue_worker_thread, args=(connection, play_queue, song_id_list[2:]))
                backgroundProcess.start()

            speech = sanitise_speech_output(f'Playing music by: {artist.value}')
            logger.info(speech)

            card = {'title': 'AskNavidrome',
                    'text': speech
                    }

            play_queue.shuffle()
            track_details = play_queue.get_next_track()
            return controller.start_playback('play', speech, card, track_details, handler_input)


class NaviSonicPlayAlbumByArtist(AbstractRequestHandler):
    """Handle NaviSonicPlayAlbumByArtist

    Play a given album by a given artist
    """

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name('NaviSonicPlayAlbumByArtist')(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        global backgroundProcess
        logger.debug('In NaviSonicPlayAlbumByArtist')

        # Check if a background process is already running, if it is then terminate the process
        # in favour of the new process.
        if backgroundProcess is not None:
            backgroundProcess.terminate()
            backgroundProcess.join()

        # Get variables from intent
        artist = get_slot_value_v2(handler_input, 'artist')
        album = get_slot_value_v2(handler_input, 'album')

        if artist is not None and album is not None:
            # Play album by artist method
            logger.debug(f'Searching for the album {album.value} by {artist.value}')

            # Search for an artist
            artist_lookup = connection.search_artist_fuzzy(artist.value, catalog, fuzzy_threshold)

            if artist_lookup is None:
                text = sanitise_speech_output(f"I couldn't find the artist {artist.value} in the collection.")
                handler_input.response_builder.speak(text).ask(text)

                return handler_input.response_builder.response

            else:
                artist_album_lookup = connection.albums_by_artist(artist_lookup[0].get('id'))

                matched_album = fuzzy_find_album(artist_album_lookup, album.value, fuzzy_threshold)

                if not matched_album:
                    text = sanitise_speech_output(f"I couldn't find an album called {album.value} by {artist.value} in the collection.")
                    handler_input.response_builder.speak(text).ask(text)

                    return handler_input.response_builder.response

                # At this point we have found an album that matches
                song_id_list = connection.build_song_list_from_albums([matched_album], -1)
                play_queue.clear()

                # Work around the Amazon / Alexa 8 second timeout.
                controller.enqueue_songs(connection, play_queue, song_id_list[:2])
                if song_id_list[2:]:
                    backgroundProcess = Process(target=queue_worker_thread, args=(connection, play_queue, song_id_list[2:]))
                    backgroundProcess.start()

                speech = sanitise_speech_output(f'Playing {album.value} by: {artist.value}')
                logger.info(speech)
                card = {'title': 'AskNavidrome',
                        'text': speech
                        }
                track_details = play_queue.get_next_track()

                return controller.start_playback('play', speech, card, track_details, handler_input)

        elif artist is None and album:
            # Play album method
            logger.debug(f'Searching for the album {album.value}')

            result = connection.search_album(album.value)

            if result is None:
                text = sanitise_speech_output(f"I couldn't find the album {album.value} in the collection.")
                handler_input.response_builder.speak(text).ask(text)

                return handler_input.response_builder.response

            else:
                song_id_list = connection.build_song_list_from_albums(result, -1)
                play_queue.clear()

                # Work around the Amazon / Alexa 8 second timeout.
                controller.enqueue_songs(connection, play_queue, song_id_list[:2])
                if song_id_list[2:]:
                    backgroundProcess = Process(target=queue_worker_thread, args=(connection, play_queue, song_id_list[2:]))
                    backgroundProcess.start()

                speech = sanitise_speech_output(f'Playing {album.value}')
                logger.info(speech)
                card = {'title': 'AskNavidrome',
                        'text': speech
                        }
                track_details = play_queue.get_next_track()

                return controller.start_playback('play', speech, card, track_details, handler_input)


class NaviSonicPlaySongByArtist(AbstractRequestHandler):
    """Handle the NaviSonicPlaySongByArtist intent

    Play the given song by the given artist if it exists in the
    collection.
    """

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name('NaviSonicPlaySongByArtist')(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        logger.debug('In NaviSonicPlaySongByArtist')

        # Get variables from intent
        artist = get_slot_value_v2(handler_input, 'artist')
        song = get_slot_value_v2(handler_input, 'song')

        logger.debug(f'Searching for the song {song.value} by {artist.value}')

        # Search for the artist
        artist_lookup = connection.search_artist_fuzzy(artist.value, catalog, fuzzy_threshold)

        if artist_lookup is None:
            text = sanitise_speech_output(f"I couldn't find the artist {artist.value} in the collection.")
            handler_input.response_builder.speak(text).ask(text)

            return handler_input.response_builder.response

        else:
            artist_id = artist_lookup[0].get('id')

            # Search for song
            song_list = connection.search_song(song.value)

            # Search for song by given artist.
            song_dets = [item.get('id') for item in song_list if item.get('artistId') == artist_id]

            if not song_dets:
                text = sanitise_speech_output(f"I couldn't find a song called {song.value} by {artist.value} in the collection.")
                handler_input.response_builder.speak(text).ask(text)

                return handler_input.response_builder.response

            play_queue.clear()
            controller.enqueue_songs(connection, play_queue, song_dets)

            speech = sanitise_speech_output(f'Playing {song.value} by {artist.value}')
            logger.info(speech)
            card = {'title': 'AskNavidrome',
                    'text': speech
                    }
            track_details = play_queue.get_next_track()

            return controller.start_playback('play', speech, card, track_details, handler_input)


class NaviSonicPlayPlaylist(AbstractRequestHandler):
    """Handle NaviSonicPlayPlaylist

    Play the given playlist
    """

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name('NaviSonicPlayPlaylist')(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        global backgroundProcess
        logger.debug('In NaviSonicPlayPlaylist')

        # Check if a background process is already running, if it is then terminate the process
        # in favour of the new process.
        if backgroundProcess is not None:
            backgroundProcess.terminate()
            backgroundProcess.join()

        # Get the requested playlist
        playlist = get_slot_value_v2(handler_input, 'playlist')

        # Search for a playlist
        playlist_id = connection.search_playlist_fuzzy(playlist.value, fuzzy_threshold)

        if playlist_id is None:
            text = sanitise_speech_output("I couldn't find the playlist " + str(playlist.value) + ' in the collection.')
            handler_input.response_builder.speak(text).ask(text)

            return handler_input.response_builder.response

        else:
            song_id_list = connection.build_song_list_from_playlist(playlist_id)
            play_queue.clear()

            # Work around the Amazon / Alexa 8 second timeout.
            controller.enqueue_songs(connection, play_queue, song_id_list[:2])
            if song_id_list[2:]:
                backgroundProcess = Process(target=queue_worker_thread, args=(connection, play_queue, song_id_list[2:]))
                backgroundProcess.start()

            speech = sanitise_speech_output('Playing playlist ' + str(playlist.value))
            logger.info(speech)
            card = {'title': 'AskNavidrome',
                    'text': speech
                    }
            track_details = play_queue.get_next_track()

            return controller.start_playback('play', speech, card, track_details, handler_input)


class NaviSonicPlayMusicByGenre(AbstractRequestHandler):
    """ Play songs from the given genre

    50 tracks from the given genre are shuffled and played
    """

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name('NaviSonicPlayMusicByGenre')(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        global backgroundProcess
        logger.debug('In NaviSonicPlayMusicByGenre')

        # Check if a background process is already running, if it is then terminate the process
        # in favour of the new process.
        if backgroundProcess is not None:
            backgroundProcess.terminate()
            backgroundProcess.join()

        # Get the requested genre
        genre = get_slot_value_v2(handler_input, 'genre')

        # Try to resolve genre, falling back to fuzzy match
        resolved_genre = fuzzy_find_genre(catalog, genre.value, fuzzy_threshold)
        genre_to_search = resolved_genre if resolved_genre else genre.value

        song_id_list = connection.build_song_list_from_genre(genre_to_search, min_song_count)

        if song_id_list is None:
            text = sanitise_speech_output(f"I couldn't find any {genre.value} songs in the collection.")
            handler_input.response_builder.speak(text).ask(text)

            return handler_input.response_builder.response

        else:
            random.shuffle(song_id_list)
            play_queue.clear()

            # Work around the Amazon / Alexa 8 second timeout.
            controller.enqueue_songs(connection, play_queue, song_id_list[:2])
            if song_id_list[2:]:
                backgroundProcess = Process(target=queue_worker_thread, args=(connection, play_queue, song_id_list[2:]))
                backgroundProcess.start()

            speech = sanitise_speech_output(f'Playing {genre.value} music')
            logger.info(speech)
            card = {'title': 'AskNavidrome',
                    'text': speech
                    }
            track_details = play_queue.get_next_track()

            return controller.start_playback('play', speech, card, track_details, handler_input)


class NaviSonicPlayMusicRandom(AbstractRequestHandler):
    """Handle the NaviSonicPlayMusicRandom intent

    Play a random selection of music.
    """

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name('NaviSonicPlayMusicRandom')(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        global backgroundProcess
        logger.debug('In NaviSonicPlayMusicRandom')

        # Check if a background process is already running, if it is then terminate the process
        # in favour of the new process.
        if backgroundProcess is not None:
            backgroundProcess.terminate()
            backgroundProcess.join()

        song_id_list = connection.build_random_song_list(min_song_count)

        if song_id_list is None:
            text = sanitise_speech_output("I couldn't find any songs in the collection.")
            handler_input.response_builder.speak(text).ask(text)

            return handler_input.response_builder.response

        else:
            random.shuffle(song_id_list)
            play_queue.clear()

            # Work around the Amazon / Alexa 8 second timeout.
            controller.enqueue_songs(connection, play_queue, song_id_list[:2])
            if song_id_list[2:]:
                backgroundProcess = Process(target=queue_worker_thread, args=(connection, play_queue, song_id_list[2:]))
                backgroundProcess.start()

            speech = sanitise_speech_output('Playing random music')
            logger.info(speech)
            card = {'title': 'AskNavidrome',
                    'text': speech
                    }
            track_details = play_queue.get_next_track()

            return controller.start_playback('play', speech, card, track_details, handler_input)


class NaviSonicPlayFavouriteSongs(AbstractRequestHandler):
    """Handle the NaviSonicPlayFavouriteSongs intent

    Play all starred / liked songs, songs are automatically shuffled.
    """

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name('NaviSonicPlayFavouriteSongs')(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        global backgroundProcess
        logger.debug('In NaviSonicPlayFavouriteSongs')

        # Check if a background process is already running, if it is then terminate the process
        # in favour of the new process.
        if backgroundProcess is not None:
            backgroundProcess.terminate()
            backgroundProcess.join()

        song_id_list = connection.build_song_list_from_favourites()

        if song_id_list is None:
            text = sanitise_speech_output("You don't have any favourite songs in the collection.")
            handler_input.response_builder.speak(text).ask(text)

            return handler_input.response_builder.response

        else:
            random.shuffle(song_id_list)
            play_queue.clear()

            # Work around the Amazon / Alexa 8 second timeout.
            controller.enqueue_songs(connection, play_queue, song_id_list[:2])
            if song_id_list[2:]:
                backgroundProcess = Process(target=queue_worker_thread, args=(connection, play_queue, song_id_list[2:]))
                backgroundProcess.start()

            speech = sanitise_speech_output('Playing your favourite tracks.')
            logger.info(speech)
            card = {'title': 'AskNavidrome',
                    'text': speech
                    }
            track_details = play_queue.get_next_track()

            return controller.start_playback('play', speech, card, track_details, handler_input)


class NaviSonicRandomiseQueue(AbstractRequestHandler):
    """Handle NaviSonicRandomiseQueue Intent

    Shuffle the current play queue
    """

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name('NaviSonicRandomiseQueue')(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        logger.debug('In NaviSonicRandomiseQueue Handler')

        play_queue.shuffle()
        play_queue.sync()

        return handler_input.response_builder.response


class NaviSonicSongDetails(AbstractRequestHandler):
    """Handle NaviSonicSongDetails Intent

    Returns information on the track that is currently playing
    """

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name('NaviSonicSongDetails')(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        logger.debug('In NaviSonicSongDetails Handler')

        current_track = play_queue.get_current_track()

        title = sanitise_speech_output(current_track.title)
        artist = sanitise_speech_output(current_track.artist)
        album = sanitise_speech_output(current_track.album)

        text = f'This is {title} by {artist}, from the album {album}'
        handler_input.response_builder.speak(text)

        return handler_input.response_builder.response


class NaviSonicStarSong(AbstractRequestHandler):
    """Handle NaviSonicStarSong Intent

    Star / favourite the current song
    """

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name('NaviSonicStarSong')(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        logger.debug('In NaviSonicStarSong Handler')

        current_track = play_queue.get_current_track()

        song_id = current_track.id
        connection.star_entry(song_id, 'song')

        return handler_input.response_builder.response


class NaviSonicUnstarSong(AbstractRequestHandler):
    """Handle NaviSonicUnstarSong Intent

    Star / favourite the current song
    """

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name('NaviSonicUnstarSong')(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        logger.debug('In NaviSonicUnstarSong Handler')

        current_track = play_queue.get_current_track()

        song_id = current_track.id
        connection.unstar_entry(song_id, 'song')

        return handler_input.response_builder.response

class NaviSonicPlay(AbstractRequestHandler):
    """Handle NaviSonicPlay - generic free-form play intent

    Receives a raw search query from AMAZON.SearchQuery and resolves it
    server-side against artists, albums, songs, and playlists using
    fuzzy matching.
    """

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name('NaviSonicPlay')(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        global backgroundProcess
        logger.debug('In NaviSonicPlay')

        if backgroundProcess is not None:
            backgroundProcess.terminate()
            backgroundProcess.join()

        query_slot = get_slot_value_v2(handler_input, 'query')
        query = query_slot.value if query_slot else ''
        logger.info(f'Generic play query: "{query}"')

        if not query:
            text = sanitise_speech_output("I didn't catch what you want to play.")
            handler_input.response_builder.speak(text).ask(text)
            return handler_input.response_builder.response

        return self._resolve_and_play(query, handler_input)

    def _resolve_and_play(self, query: str, handler_input: HandlerInput) -> Response:
        global backgroundProcess

        # Check for "by" to split into item + artist
        query_lower = query.lower()
        if ' by ' in query_lower:
            parts = query.split(' by ', 1)
            item_part = parts[0].strip()
            artist_part = parts[1].strip()

            if item_part and artist_part:
                result = self._try_item_by_artist(item_part, artist_part, handler_input)
                if result is not None:
                    return result

        # Try as artist
        result = self._try_artist(query, handler_input)
        if result is not None:
            return result

        # Try as album
        result = self._try_album(query, handler_input)
        if result is not None:
            return result

        # Try as song
        result = self._try_song(query, handler_input)
        if result is not None:
            return result

        # Try as playlist
        result = self._try_playlist(query, handler_input)
        if result is not None:
            return result

        # Nothing matched
        text = sanitise_speech_output(f"I couldn't find anything matching {query} in the collection.")
        handler_input.response_builder.speak(text).ask(text)
        return handler_input.response_builder.response

    def _try_item_by_artist(self, item: str, artist_name: str, handler_input: HandlerInput) -> Response:
        global backgroundProcess

        artist_lookup = connection.search_artist_fuzzy(artist_name, catalog, fuzzy_threshold)
        if artist_lookup is None:
            return None

        artist_id = artist_lookup[0].get('id')
        artist_album_lookup = connection.albums_by_artist(artist_id)

        # Try as album by artist
        matched_album = fuzzy_find_album(artist_album_lookup, item, fuzzy_threshold)
        if matched_album:
            song_id_list = connection.build_song_list_from_albums([matched_album], -1)
            if song_id_list:
                return self._start_playing(song_id_list, f'Playing {item} by {artist_name}', handler_input)

        # Try as song by artist
        song_list = connection.search_song(item)
        if song_list:
            song_dets = [s.get('id') for s in song_list if s.get('artistId') == artist_id]
            if song_dets:
                play_queue.clear()
                controller.enqueue_songs(connection, play_queue, song_dets)
                speech = sanitise_speech_output(f'Playing {item} by {artist_name}')
                logger.info(speech)
                card = {'title': 'AskNavidrome', 'text': speech}
                track_details = play_queue.get_next_track()
                return controller.start_playback('play', speech, card, track_details, handler_input)

        return None

    def _try_artist(self, query: str, handler_input: HandlerInput) -> Response:
        global backgroundProcess

        artist_lookup = connection.search_artist_fuzzy(query, catalog, fuzzy_threshold)
        if artist_lookup is None:
            return None

        artist_album_lookup = connection.albums_by_artist(artist_lookup[0].get('id'))
        song_id_list = connection.build_song_list_from_albums(artist_album_lookup, min_song_count)
        if not song_id_list:
            return None

        return self._start_playing(song_id_list, f'Playing music by {query}', handler_input, shuffle=True)

    def _try_album(self, query: str, handler_input: HandlerInput) -> Response:
        global backgroundProcess

        result = connection.search_album(query)
        if result is None:
            # Try fuzzy against all albums from all artists in catalog
            return None

        song_id_list = connection.build_song_list_from_albums(result, -1)
        if not song_id_list:
            return None

        return self._start_playing(song_id_list, f'Playing {query}', handler_input)

    def _try_song(self, query: str, handler_input: HandlerInput) -> Response:
        song_list = connection.search_song(query)
        if not song_list:
            return None

        song_dets = [s.get('id') for s in song_list]
        play_queue.clear()
        controller.enqueue_songs(connection, play_queue, song_dets)

        speech = sanitise_speech_output(f'Playing {query}')
        logger.info(speech)
        card = {'title': 'AskNavidrome', 'text': speech}
        track_details = play_queue.get_next_track()
        return controller.start_playback('play', speech, card, track_details, handler_input)

    def _try_playlist(self, query: str, handler_input: HandlerInput) -> Response:
        global backgroundProcess

        playlist_id = connection.search_playlist_fuzzy(query, fuzzy_threshold)
        if playlist_id is None:
            return None

        song_id_list = connection.build_song_list_from_playlist(playlist_id)
        if not song_id_list:
            return None

        return self._start_playing(song_id_list, f'Playing playlist {query}', handler_input)

    def _start_playing(self, song_id_list: list, speech_text: str, handler_input: HandlerInput, shuffle: bool = False) -> Response:
        global backgroundProcess

        play_queue.clear()
        controller.enqueue_songs(connection, play_queue, song_id_list[:2])
        if song_id_list[2:]:
            backgroundProcess = Process(target=queue_worker_thread, args=(connection, play_queue, song_id_list[2:]))
            backgroundProcess.start()

        if shuffle:
            play_queue.shuffle()

        speech = sanitise_speech_output(speech_text)
        logger.info(speech)
        card = {'title': 'AskNavidrome', 'text': speech}
        track_details = play_queue.get_next_track()
        return controller.start_playback('play', speech, card, track_details, handler_input)


#
# AudioPlayer Handlers
#


class PlaybackStartedHandler(AbstractRequestHandler):
    """AudioPlayer.PlaybackStarted Directive received.

    Confirming that the requested audio file began playing.
    Do not send any specific response.
    """

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_request_type('AudioPlayer.PlaybackStarted')(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        logger.debug('In PlaybackStartedHandler')
        logger.info('Playback started')

        return handler_input.response_builder.response


class PlaybackStoppedHandler(AbstractRequestHandler):
    """AudioPlayer.PlaybackStopped Directive received.

    Confirming that the requested audio file stopped playing.
    Do not send any specific response.
    """

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_request_type('AudioPlayer.PlaybackStopped')(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        logger.debug('In PlaybackStoppedHandler')

        # store the current offset for later resumption
        play_queue.set_current_track_offset(handler_input.request_envelope.request.offset_in_milliseconds)

        current_track = play_queue.get_current_track()
        logger.debug(f'Stored track offset of: {current_track.offset} ms for {current_track.title}')
        logger.info('Playback stopped')

        return handler_input.response_builder.response


class PlaybackNearlyFinishedHandler(AbstractRequestHandler):
    """AudioPlayer.PlaybackNearlyFinished Directive received.

    Replacing queue with the URL again. This should not happen on live streams.
    """

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_request_type('AudioPlayer.PlaybackNearlyFinished')(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        logger.debug('In PlaybackNearlyFinishedHandler')
        logger.info('Queuing next track...')
        track_details = play_queue.enqueue_next_track()

        if track_details is None:
            logger.info('No more tracks to enqueue, end of playlist')
            return handler_input.response_builder.response

        return controller.start_playback('continue', None, None, track_details, handler_input)


class PlaybackFinishedHandler(AbstractRequestHandler):
    """AudioPlayer.PlaybackFinished Directive received.

    Confirming that the requested audio file completed playing.
    Do not send any specific response.
    """

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_request_type('AudioPlayer.PlaybackFinished')(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        logger.debug('In PlaybackFinishedHandler')

        # Generate a timestamp for scrobbling
        # py-sonic's scrobble() converts to milliseconds internally via _ts2milli()
        listen_time = datetime.now().timestamp()
        current_track = play_queue.get_current_track()
        connection.scrobble(current_track.id, listen_time)
        play_queue.get_next_track()

        return handler_input.response_builder.response


class PausePlaybackHandler(AbstractRequestHandler):
    """Handler for stopping audio.

    Handles Stop, Cancel and Pause Intents and PauseCommandIssued event.
    """

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return (is_intent_name('AMAZON.StopIntent')(handler_input) or
                is_intent_name('AMAZON.CancelIntent')(handler_input) or
                is_intent_name('AMAZON.PauseIntent')(handler_input))

    def handle(self, handler_input: HandlerInput) -> Response:
        logger.debug('In PausePlaybackHandler')
        play_queue.sync()

        return controller.stop(handler_input)


class ResumePlaybackHandler(AbstractRequestHandler):
    """Handler for resuming audio on different events.

    Handles PlayAudio Intent, Resume Intent.
    """

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return (is_intent_name('AMAZON.ResumeIntent')(handler_input) or
                is_intent_name('PlayAudio')(handler_input))

    def handle(self, handler_input: HandlerInput) -> Response:
        logger.debug('In ResumePlaybackHandler')

        current_track = play_queue.get_current_track()

        if current_track.offset > 0:
            # There is a paused track, continue
            logger.info('Resuming ' + str(current_track.title))
            logger.info('Offset ' + str(current_track.offset))

            return controller.start_playback('play', None, None, current_track, handler_input)

        elif play_queue.get_queue_count() > 0 and current_track.offset == 0:
            # No paused tracks but tracks in queue
            logger.info('Resuming - There was no paused track, getting next track from queue')
            track_details = play_queue.get_next_track()

            return controller.start_playback('play', None, None, track_details, handler_input)


class NextPlaybackHandler(AbstractRequestHandler):
    """Handle NextIntent"""

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return (is_intent_name('AMAZON.NextIntent')(handler_input) or
                is_request_type('PlaybackController.NextCommandIssued')(handler_input))

    def handle(self, handler_input: HandlerInput) -> Response:
        logger.debug('In NextPlaybackHandler')

        track_details = play_queue.get_next_track()

        # Set the offset to 0 as we are skipping we want to start at the beginning
        track_details.offset = 0

        return controller.start_playback('play', None, None, track_details, handler_input)


class PreviousPlaybackHandler(AbstractRequestHandler):
    """Handle PreviousIntent"""

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return (is_intent_name('AMAZON.PreviousIntent')(handler_input) or
                is_request_type('PlaybackController.PreviousCommandIssued')(handler_input))

    def handle(self, handler_input: HandlerInput) -> Response:
        logger.debug('In PreviousPlaybackHandler')
        track_details = play_queue.get_previous_track()

        # Set the offset to 0 as we are skipping we want to start at the beginning
        track_details.offset = 0

        return controller.start_playback('play', None, None, track_details, handler_input)


class PlaybackFailedEventHandler(AbstractRequestHandler):
    """AudioPlayer.PlaybackFailed Directive received.

    Logging the error and restarting playing with no output speech.
    """

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_request_type('AudioPlayer.PlaybackFailed')(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        logger.debug('In PlaybackFailedHandler')

        current_track = play_queue.get_current_track()
        song_id = current_track.id

        # Log failure and track ID
        logger.error(f'Playback Failed: {handler_input.request_envelope.request.error}')
        logger.error(f'Failed playing track with ID: {song_id}')

        # Skip to the next track instead of stopping
        track_details = play_queue.get_next_track()

        # Set the offset to 0 as we are skipping we want to start at the beginning
        track_details.offset = 0

        return controller.start_playback('play', None, None, track_details, handler_input)


#
# Exception Handers
#


class SystemExceptionHandler(AbstractExceptionHandler):
    """Handle System.ExceptionEncountered

    Handles exceptions and prints error information
    in the log
    """

    def can_handle(self, handler_input: HandlerInput, exception: Exception) -> bool:
        return is_request_type('System.ExceptionEncountered')(handler_input)

    def handle(self, handler_input: HandlerInput, exception: Exception) -> Response:
        logger.debug('In SystemExceptionHandler')

        # Log the exception
        logger.error(f'System Exception: {exception}')
        logger.error(f'Request Type Was: {get_request_type(handler_input)}')
        error = handler_input.request_envelope.request.to_dict()
        logger.error(f"Details: {error.get('error').get('message')}")

        if get_request_type(handler_input) == 'IntentRequest':
            logger.error(f'Intent Name Was: {get_intent_name(handler_input)}')

        speech = sanitise_speech_output("Sorry, I didn't get that. Can you please say it again!!")
        handler_input.response_builder.speak(speech).ask(speech)

        return handler_input.response_builder.response


class GeneralExceptionHandler(AbstractExceptionHandler):
    """Handle general exceptions

    Handles exceptions and prints error information
    in the log
    """

    def can_handle(self, handler_input: HandlerInput, exception: Exception) -> bool:
        return True

    def handle(self, handler_input: HandlerInput, exception: Exception) -> Response:
        logger.debug('In GeneralExceptionHandler')

        # Log the exception
        logger.error(f'General Exception: {exception}')
        logger.error(f'Request Type Was: {get_request_type(handler_input)}')

        if get_request_type(handler_input) == 'IntentRequest':
            logger.error(f'Intent Name Was: {get_intent_name(handler_input)}')

        speech = sanitise_speech_output("Sorry, I didn't get that. Can you please say it again!!")
        handler_input.response_builder.speak(speech).ask(speech)

        return handler_input.response_builder.response


#
# Request Interceptors
#


class LoggingRequestInterceptor(AbstractRequestInterceptor):
    """Intercept all requests

    Intercepts all requests sent to the skill and prints them in the log
    """

    def process(self, handler_input: HandlerInput):
        logger.debug(f'Request received: {handler_input.request_envelope.request}')


class LoggingResponseInterceptor(AbstractResponseInterceptor):
    """Intercept all responses

    Intercepts all responses sent from the skill and prints them in the log
    """

    def process(self, handler_input: HandlerInput, response: Response):
        logger.debug(f'Response sent: {response}')

#
# Functions
#


def sanitise_speech_output(speech_string: str) -> str:
    """Sanitise speech output inline with the SSML standard

    Speech Synthesis Markup Language (SSML) has certain ASCII characters that are
    reserved.  This function replaces them with alternatives.

    :param speech_string: The string to process
    :type speech_string: str
    :return: The processed SSML compliant string
    :rtype: str
    """

    logger.debug('In sanitise_speech_output()')

    if '&' in speech_string:
        speech_string = speech_string.replace('&', 'and')
    if '/' in speech_string:
        speech_string = speech_string.replace('/', 'and')
    if '\\' in speech_string:
        speech_string = speech_string.replace('\\', 'and')
    if '"' in speech_string:
        speech_string = speech_string.replace('"', '')
    if "'" in speech_string:
        speech_string = speech_string.replace("'", "")
    if "<" in speech_string:
        speech_string = speech_string.replace('<', '')
    if ">" in speech_string:
        speech_string = speech_string.replace('>', '')

    return speech_string


def queue_worker_thread(connection: object, play_queue: object, song_id_list: list) -> None:
    """Media queue worker

    This function allows media queues to be populated in the background enabling multithreading
    and increasing skill response times.

    :param connection: A SubSonic API connection object
    :type connection: object
    :param play_queue: A MediaQueue object
    :type play_queue: object
    :param song_id_list: A list containing Navidrome song IDs
    :type song_id_list: list
    """

    logger.debug('In playlist processing thread!')
    controller.enqueue_songs(connection, play_queue, song_id_list)
    play_queue.sync()
    logger.debug('Finished playlist processing!')


# Register Intent Handlers
sb.add_request_handler(LaunchRequestHandler())
sb.add_request_handler(CheckAudioInterfaceHandler())
sb.add_request_handler(SkillEventHandler())
sb.add_request_handler(HelpHandler())
sb.add_request_handler(NaviSonicPlayMusicByArtist())
sb.add_request_handler(NaviSonicPlayAlbumByArtist())
sb.add_request_handler(NaviSonicPlaySongByArtist())
sb.add_request_handler(NaviSonicPlayPlaylist())
sb.add_request_handler(NaviSonicPlayFavouriteSongs())
sb.add_request_handler(NaviSonicPlayMusicByGenre())
sb.add_request_handler(NaviSonicPlayMusicRandom())
sb.add_request_handler(NaviSonicRandomiseQueue())
sb.add_request_handler(NaviSonicSongDetails())
sb.add_request_handler(NaviSonicStarSong())
sb.add_request_handler(NaviSonicUnstarSong())
sb.add_request_handler(NaviSonicPlay())

# Register AutoPlayer Handlers
sb.add_request_handler(PlaybackStartedHandler())
sb.add_request_handler(PlaybackStoppedHandler())
sb.add_request_handler(PlaybackNearlyFinishedHandler())
sb.add_request_handler(PlaybackFinishedHandler())
sb.add_request_handler(PausePlaybackHandler())
sb.add_request_handler(NextPlaybackHandler())
sb.add_request_handler(PreviousPlaybackHandler())
sb.add_request_handler(ResumePlaybackHandler())
sb.add_request_handler(PlaybackFailedEventHandler())


# Register Exception Handlers
sb.add_exception_handler(SystemExceptionHandler())
sb.add_exception_handler(GeneralExceptionHandler())

if navidrome_log_level >= 2:
    # Register Interceptors (log all requests)
    sb.add_global_request_interceptor(LoggingRequestInterceptor())
    sb.add_global_response_interceptor(LoggingResponseInterceptor())

sa = SkillAdapter(skill=sb.create(), skill_id='test', app=app)
sa.register(app=app, route='/')

# Enable queue and history diagnostics
if navidrome_log_level == 3:
    logger.warning('AskNavidrome debugging has been enabled, this should only be used when testing!')
    logger.warning('The /buffer, /queue and /history http endpoints are available publicly!')

    @app.route('/queue')
    def view_queue():
        """View the contents of play_queue.queue

        Creates a tabulated page containing the contents of the play_queue.queue deque.
        """

        current_track = play_queue.get_current_track()

        return render_template('table.html', title='AskNavidrome - Queued Tracks',
                               tracks=play_queue.get_current_queue(), current=current_track)

    @app.route('/history')
    def view_history():
        """View the contents of play_queue.history

        Creates a tabulated page containing the contents of the play_queue.history deque.
        """

        current_track = play_queue.get_current_track()

        return render_template('table.html', title='AskNavidrome - Track History',
                               tracks=play_queue.get_history(), current=current_track)

    @app.route('/buffer')
    def view_buffer():
        """View the contents of play_queue.buffer

        Creates a tabulated page containing the contents of the play_queue.buffer deque.
        """

        current_track = play_queue.get_current_track()

        return render_template('table.html', title='AskNavidrome - Buffered Tracks',
                               tracks=play_queue.get_buffer(), current=current_track)


# Run web app by default when file is executed.
if __name__ == '__main__':
    # Start the web service
    app.run(host='0.0.0.0')

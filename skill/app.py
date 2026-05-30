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

# Create web service
app = Flask(__name__)

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

try:
    if 'NAVI_SKILL_ID' in os.environ:
        sb.skill_id = os.getenv('NAVI_SKILL_ID')
        logger.info(f'Skill ID set to: {sb.skill_id}')
    else:
        raise NameError
except NameError as err:
    logger.error(f'The Alexa skill ID was not found! {err}')
    raise

try:
    if 'NAVI_SONG_COUNT' in os.environ:
        min_song_count = os.getenv('NAVI_SONG_COUNT')
        logger.info(f'Minimum song count is set to: {min_song_count}')
    else:
        raise NameError
except NameError as err:
    logger.error(f'The minimum song count was not found! {err}')
    raise

try:
    if 'NAVI_URL' in os.environ:
        navidrome_url = os.getenv('NAVI_URL')
        logger.info(f'The URL for Navidrome is set to: {navidrome_url}')
    else:
        raise NameError
except NameError as err:
    logger.error(f'The URL of the Navidrome server was not found! {err}')
    raise

try:
    if 'NAVI_USER' in os.environ:
        navidrome_user = os.getenv('NAVI_USER')
        logger.info(f'The Navidrome user name is set to: {navidrome_user}')
    else:
        raise NameError
except NameError as err:
    logger.error(f'The Navidrome user name was not found! {err}')
    raise

try:
    if 'NAVI_PASS' in os.environ:
        navidrome_passwd = os.getenv('NAVI_PASS')
        logger.info('The Navidrome password is set')
    else:
        raise NameError
except NameError as err:
    logger.error(f'The Navidrome password was not found! {err}')
    raise

try:
    if 'NAVI_PORT' in os.environ:
        navidrome_port = os.getenv('NAVI_PORT')
        logger.info(f'The Navidrome port is set to: {navidrome_port}')
    else:
        raise NameError
except NameError as err:
    logger.error(f'The Navidrome port was not found! {err}')
    raise

try:
    if 'NAVI_API_PATH' in os.environ:
        navidrome_api_location = os.getenv('NAVI_API_PATH')
        logger.info(f'The Navidrome API path is set to: {navidrome_api_location}')
    else:
        raise NameError
except NameError as err:
    logger.error(f'The Navidrome API path was not found! {err}')
    raise

try:
    if 'NAVI_API_VER' in os.environ:
        navidrome_api_version = os.getenv('NAVI_API_VER')
        logger.info(f'The Navidrome API version is set to: {navidrome_api_version}')
    else:
        raise NameError
except NameError as err:
    logger.error(f'The Navidrome API version was not found! {err}')
    raise

logger.debug('Configuration has been successfully loaded')

# Set log level based on config value
if 'NAVI_DEBUG' in os.environ:
    navidrome_log_level = int(os.getenv('NAVI_DEBUG'))

    if navidrome_log_level == 0:
        logger.setLevel(logging.WARNING)
        logger.warning('Log level set to WARNING')
    elif navidrome_log_level == 1:
        logger.setLevel(logging.INFO)
        logger.info('Log level set to INFO')
    elif navidrome_log_level == 2:
        logger.setLevel(logging.DEBUG)
        logger.debug('Log level set to DEBUG')
    elif navidrome_log_level == 3:
        logger.setLevel(logging.DEBUG)
        logger.debug('Log level set to DEBUG')
    else:
        navidrome_log_level = 0
        logger.setLevel(logging.WARNING)
        logger.warning('Log level set to WARNING')

# Create a shareable queue
BaseManager.register('MediaQueue', queue.MediaQueue)
manager = BaseManager()
manager.start()
play_queue = manager.MediaQueue()
logger.debug('MediaQueue object created...')

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
except:
    raise RuntimeError('Could not connect to SubSonic API!')

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
        speech = sanitise_speech_output('Bereit!')

        handler_input.response_builder.speak(speech).ask(speech)
        return handler_input.response_builder.response


class CheckAudioInterfaceHandler(AbstractRequestHandler):
    """Check if device supports audio play."""

    def can_handle(self, handler_input: HandlerInput) -> bool:
        if handler_input.request_envelope.context.system.device:
            return False
        else:
            return False

    def handle(self, handler_input: HandlerInput) -> Response:
        logger.debug('In CheckAudioInterfaceHandler')

        _ = handler_input.attributes_manager.request_attributes['_']
        handler_input.response_builder.speak('Dieses Gerät wird nicht unterstützt.').set_should_end_session(True)

        return handler_input.response_builder.response


class SkillEventHandler(AbstractRequestHandler):
    """Close session for skill events or when session ends."""

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

        text = sanitise_speech_output('AskNavidrome ermöglicht die Wiedergabe deiner Musikbibliothek über Navidrome.')
        handler_input.response_builder.speak(text)

        return handler_input.response_builder.response


class NaviSonicPlayMusicByArtist(AbstractRequestHandler):
    """Play a selection of songs for the given artist"""

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name('NaviSonicPlayMusicByArtist')(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        global backgroundProcess
        logger.debug('In NaviSonicPlayMusicByArtist')

        if backgroundProcess is not None:
            backgroundProcess.terminate()
            backgroundProcess.join()

        artist = get_slot_value_v2(handler_input, 'artist')
        artist_lookup = connection.search_artist(artist.value)

        if artist_lookup is None:
            text = sanitise_speech_output(f"Ich konnte den Künstler {artist.value} nicht in der Bibliothek finden.")
            handler_input.response_builder.speak(text).ask(text)
            return handler_input.response_builder.response

        else:
            artist_album_lookup = connection.albums_by_artist(artist_lookup[0].get('id'))
            song_id_list = connection.build_song_list_from_albums(artist_album_lookup, min_song_count)
            play_queue.clear()

            controller.enqueue_songs(connection, play_queue, [song_id_list[0], song_id_list[1]])
            backgroundProcess = Process(target=queue_worker_thread, args=(connection, play_queue, song_id_list[2:]))
            backgroundProcess.start()

            speech = sanitise_speech_output(f'Ich spiele Musik von: {artist.value}')
            logger.info(speech)

            card = {'title': 'AskNavidrome', 'text': speech}

            play_queue.shuffle()
            track_details = play_queue.get_next_track()
            return controller.start_playback('play', speech, card, track_details, handler_input)


class NaviSonicPlayAlbumByArtist(AbstractRequestHandler):
    """Play a given album by a given artist"""

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name('NaviSonicPlayAlbumByArtist')(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        global backgroundProcess
        logger.debug('In NaviSonicPlayAlbumByArtist')

        if backgroundProcess is not None:
            backgroundProcess.terminate()
            backgroundProcess.join()

        artist = get_slot_value_v2(handler_input, 'artist')
        album = get_slot_value_v2(handler_input, 'album')

        if artist is not None and album is not None:
            logger.debug(f'Searching for the album {album.value} by {artist.value}')

            artist_lookup = connection.search_artist(artist.value)

            if artist_lookup is None:
                text = sanitise_speech_output(f"Ich konnte den Künstler {artist.value} nicht in der Bibliothek finden.")
                handler_input.response_builder.speak(text).ask(text)
                return handler_input.response_builder.response

            else:
                artist_album_lookup = connection.albums_by_artist(artist_lookup[0].get('id'))
                result = [album_result for album_result in artist_album_lookup if album_result.get('name').lower() == album.value.lower()]

                if not result:
                    text = sanitise_speech_output(f"Ich konnte das Album {album.value} von {artist.value} nicht in der Bibliothek finden.")
                    handler_input.response_builder.speak(text).ask(text)
                    return handler_input.response_builder.response

                song_id_list = connection.build_song_list_from_albums(result, -1)
                play_queue.clear()

                controller.enqueue_songs(connection, play_queue, [song_id_list[0], song_id_list[1]])
                backgroundProcess = Process(target=queue_worker_thread, args=(connection, play_queue, song_id_list[2:]))
                backgroundProcess.start()

                speech = sanitise_speech_output(f'Ich spiele {album.value} von: {artist.value}')
                logger.info(speech)
                card = {'title': 'AskNavidrome', 'text': speech}
                track_details = play_queue.get_next_track()

                return controller.start_playback('play', speech, card, track_details, handler_input)

        elif artist is None and album:
            logger.debug(f'Searching for the album {album.value}')

            result = connection.search_album(album.value)

            if result is None:
                text = sanitise_speech_output(f"Ich konnte das Album {album.value} nicht in der Bibliothek finden.")
                handler_input.response_builder.speak(text).ask(text)
                return handler_input.response_builder.response

            else:
                song_id_list = connection.build_song_list_from_albums(result, -1)
                play_queue.clear()

                controller.enqueue_songs(connection, play_queue, [song_id_list[0], song_id_list[1]])
                backgroundProcess = Process(target=queue_worker_thread, args=(connection, play_queue, song_id_list[2:]))
                backgroundProcess.start()

                speech = sanitise_speech_output(f'Ich spiele {album.value}')
                logger.info(speech)
                card = {'title': 'AskNavidrome', 'text': speech}
                track_details = play_queue.get_next_track()

                return controller.start_playback('play', speech, card, track_details, handler_input)


class NaviSonicPlaySongByArtist(AbstractRequestHandler):
    """Play the given song by the given artist"""

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name('NaviSonicPlaySongByArtist')(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        logger.debug('In NaviSonicPlaySongByArtist')

        artist = get_slot_value_v2(handler_input, 'artist')
        song = get_slot_value_v2(handler_input, 'song')

        logger.debug(f'Searching for the song {song.value} by {artist.value}')

        artist_lookup = connection.search_artist(artist.value)

        if artist_lookup is None:
            text = sanitise_speech_output(f"Ich konnte den Künstler {artist.value} nicht in der Bibliothek finden.")
            handler_input.response_builder.speak(text).ask(text)
            return handler_input.response_builder.response

        else:
            artist_id = artist_lookup[0].get('id')
            song_list = connection.search_song(song.value)
            song_dets = [item.get('id') for item in song_list if item.get('artistId') == artist_id]

            if not song_dets:
                text = sanitise_speech_output(f"Ich konnte den Song {song.value} von {artist.value} nicht in der Bibliothek finden.")
                handler_input.response_builder.speak(text).ask(text)
                return handler_input.response_builder.response

            play_queue.clear()
            controller.enqueue_songs(connection, play_queue, song_dets)

            speech = sanitise_speech_output(f'Ich spiele {song.value} von {artist.value}')
            logger.info(speech)
            card = {'title': 'AskNavidrome', 'text': speech}
            track_details = play_queue.get_next_track()

            return controller.start_playback('play', speech, card, track_details, handler_input)


class NaviSonicPlayPlaylist(AbstractRequestHandler):
    """Play the given playlist"""

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name('NaviSonicPlayPlaylist')(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        global backgroundProcess
        logger.debug('In NaviSonicPlayPlaylist')

        if backgroundProcess is not None:
            backgroundProcess.terminate()
            backgroundProcess.join()

        playlist = get_slot_value_v2(handler_input, 'playlist')
        playlist_id = connection.search_playlist(playlist.value)

        if playlist_id is None:
            text = sanitise_speech_output("Ich konnte die Playlist " + str(playlist.value) + ' nicht in der Bibliothek finden.')
            handler_input.response_builder.speak(text).ask(text)
            return handler_input.response_builder.response

        else:
            song_id_list = connection.build_song_list_from_playlist(playlist_id)
            play_queue.clear()

            controller.enqueue_songs(connection, play_queue, [song_id_list[0], song_id_list[1]])
            backgroundProcess = Process(target=queue_worker_thread, args=(connection, play_queue, song_id_list[2:]))
            backgroundProcess.start()

            speech = sanitise_speech_output('Ich spiele die Playlist ' + str(playlist.value))
            logger.info(speech)
            card = {'title': 'AskNavidrome', 'text': speech}
            track_details = play_queue.get_next_track()

            return controller.start_playback('play', speech, card, track_details, handler_input)


class NaviSonicPlayMusicByGenre(AbstractRequestHandler):
    """Play songs from the given genre"""

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name('NaviSonicPlayMusicByGenre')(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        global backgroundProcess
        logger.debug('In NaviSonicPlayMusicByGenre')

        if backgroundProcess is not None:
            backgroundProcess.terminate()
            backgroundProcess.join()

        genre = get_slot_value_v2(handler_input, 'genre')
        song_id_list = connection.build_song_list_from_genre(genre.value, min_song_count)

        if song_id_list is None:
            text = sanitise_speech_output(f"Ich konnte keine {genre.value} Songs in der Bibliothek finden.")
            handler_input.response_builder.speak(text).ask(text)
            return handler_input.response_builder.response

        else:
            random.shuffle(song_id_list)
            play_queue.clear()

            controller.enqueue_songs(connection, play_queue, [song_id_list[0], song_id_list[1]])
            backgroundProcess = Process(target=queue_worker_thread, args=(connection, play_queue, song_id_list[2:]))
            backgroundProcess.start()

            speech = sanitise_speech_output(f'Ich spiele {genre.value} Musik')
            logger.info(speech)
            card = {'title': 'AskNavidrome', 'text': speech}
            track_details = play_queue.get_next_track()

            return controller.start_playback('play', speech, card, track_details, handler_input)


class NaviSonicPlayMusicRandom(AbstractRequestHandler):
    """Play a random selection of music."""

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name('NaviSonicPlayMusicRandom')(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        global backgroundProcess
        logger.debug('In NaviSonicPlayMusicRandom')

        if backgroundProcess is not None:
            backgroundProcess.terminate()
            backgroundProcess.join()

        song_id_list = connection.build_random_song_list(min_song_count)

        if song_id_list is None:
            text = sanitise_speech_output("Ich konnte keine Songs in der Bibliothek finden.")
            handler_input.response_builder.speak(text).ask(text)
            return handler_input.response_builder.response

        else:
            random.shuffle(song_id_list)
            play_queue.clear()

            controller.enqueue_songs(connection, play_queue, [song_id_list[0], song_id_list[1]])
            backgroundProcess = Process(target=queue_worker_thread, args=(connection, play_queue, song_id_list[2:]))
            backgroundProcess.start()

            speech = sanitise_speech_output('Ich spiele zufällige Musik')
            logger.info(speech)
            card = {'title': 'AskNavidrome', 'text': speech}
            track_details = play_queue.get_next_track()

            return controller.start_playback('play', speech, card, track_details, handler_input)


class NaviSonicPlayFavouriteSongs(AbstractRequestHandler):
    """Play all starred / liked songs."""

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name('NaviSonicPlayFavouriteSongs')(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        global backgroundProcess
        logger.debug('In NaviSonicPlayFavouriteSongs')

        if backgroundProcess is not None:
            backgroundProcess.terminate()
            backgroundProcess.join()

        song_id_list = connection.build_song_list_from_favourites()

        if song_id_list is None:
            text = sanitise_speech_output("Du hast keine Favoriten in der Bibliothek.")
            handler_input.response_builder.speak(text).ask(text)
            return handler_input.response_builder.response

        else:
            random.shuffle(song_id_list)
            play_queue.clear()

            controller.enqueue_songs(connection, play_queue, [song_id_list[0], song_id_list[1]])
            backgroundProcess = Process(target=queue_worker_thread, args=(connection, play_queue, song_id_list[2:]))
            backgroundProcess.start()

            speech = sanitise_speech_output('Ich spiele deine Favoriten.')
            logger.info(speech)
            card = {'title': 'AskNavidrome', 'text': speech}
            track_details = play_queue.get_next_track()

            return controller.start_playback('play', speech, card, track_details, handler_input)


class NaviSonicRandomiseQueue(AbstractRequestHandler):
    """Shuffle the current play queue"""

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name('NaviSonicRandomiseQueue')(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        logger.debug('In NaviSonicRandomiseQueue Handler')

        play_queue.shuffle()
        play_queue.sync()

        return handler_input.response_builder.response


class NaviSonicSongDetails(AbstractRequestHandler):
    """Returns information on the track that is currently playing"""

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name('NaviSonicSongDetails')(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        logger.debug('In NaviSonicSongDetails Handler')

        current_track = play_queue.get_current_track()

        title = sanitise_speech_output(current_track.title)
        artist = sanitise_speech_output(current_track.artist)
        album = sanitise_speech_output(current_track.album)

        text = f'Das ist {title} von {artist}, vom Album {album}'
        handler_input.response_builder.speak(text)

        return handler_input.response_builder.response


class NaviSonicStarSong(AbstractRequestHandler):
    """Star / favourite the current song"""

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name('NaviSonicStarSong')(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        logger.debug('In NaviSonicStarSong Handler')

        current_track = play_queue.get_current_track()
        song_id = current_track.id
        connection.star_entry(song_id, 'song')

        return handler_input.response_builder.response


class NaviSonicUnstarSong(AbstractRequestHandler):
    """Unstar the current song"""

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name('NaviSonicUnstarSong')(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        logger.debug('In NaviSonicUnstarSong Handler')

        current_track = play_queue.get_current_track()
        song_id = current_track.id
        connection.star_entry(song_id, 'song')
        connection.unstar_entry(song_id, 'song')

        return handler_input.response_builder.response

#
# AudioPlayer Handlers
#


class PlaybackStartedHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_request_type('AudioPlayer.PlaybackStarted')(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        logger.debug('In PlaybackStartedHandler')
        logger.info('Playback started')
        return handler_input.response_builder.response


class PlaybackStoppedHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_request_type('AudioPlayer.PlaybackStopped')(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        logger.debug('In PlaybackStoppedHandler')
        play_queue.set_current_track_offset(handler_input.request_envelope.request.offset_in_milliseconds)
        current_track = play_queue.get_current_track()
        logger.debug(f'Stored track offset of: {current_track.offset} ms for {current_track.title}')
        logger.info('Playback stopped')
        return handler_input.response_builder.response


class PlaybackNearlyFinishedHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_request_type('AudioPlayer.PlaybackNearlyFinished')(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        logger.debug('In PlaybackNearlyFinishedHandler')
        logger.info('Queuing next track...')
        track_details = play_queue.enqueue_next_track()
        return controller.start_playback('continue', None, None, track_details, handler_input)


class PlaybackFinishedHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_request_type('AudioPlayer.PlaybackFinished')(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        logger.debug('In PlaybackFinishedHandler')
        timestamp_ms = datetime.now().timestamp()
        current_track = play_queue.get_current_track()
        connection.scrobble(current_track.id, timestamp_ms)
        play_queue.get_next_track()
        return handler_input.response_builder.response


class PausePlaybackHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return (is_intent_name('AMAZON.StopIntent')(handler_input) or
                is_intent_name('AMAZON.CancelIntent')(handler_input) or
                is_intent_name('AMAZON.PauseIntent')(handler_input))

    def handle(self, handler_input: HandlerInput) -> Response:
        logger.debug('In PausePlaybackHandler')
        play_queue.sync()
        return controller.stop(handler_input)


class ResumePlaybackHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return (is_intent_name('AMAZON.ResumeIntent')(handler_input) or
                is_intent_name('PlayAudio')(handler_input))

    def handle(self, handler_input: HandlerInput) -> Response:
        logger.debug('In ResumePlaybackHandler')
        current_track = play_queue.get_current_track()

        if current_track.offset > 0:
            logger.info('Resuming ' + str(current_track.title))
            return controller.start_playback('play', None, None, current_track, handler_input)

        elif play_queue.get_queue_count() > 0 and current_track.offset == 0:
            logger.info('Resuming - There was no paused track, getting next track from queue')
            track_details = play_queue.get_next_track()
            return controller.start_playback('play', None, None, track_details, handler_input)


class NextPlaybackHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return (is_intent_name('AMAZON.NextIntent')(handler_input) or
                is_request_type('PlaybackController.NextCommandIssued')(handler_input))

    def handle(self, handler_input: HandlerInput) -> Response:
        logger.debug('In NextPlaybackHandler')
        track_details = play_queue.get_next_track()
        track_details.offset = 0
        return controller.start_playback('play', None, None, track_details, handler_input)


class PreviousPlaybackHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return (is_intent_name('AMAZON.PreviousIntent')(handler_input) or
                is_request_type('PlaybackController.PreviousCommandIssued')(handler_input))

    def handle(self, handler_input: HandlerInput) -> Response:
        logger.debug('In PreviousPlaybackHandler')
        track_details = play_queue.get_previous_track()
        track_details.offset = 0
        return controller.start_playback('play', None, None, track_details, handler_input)


class PlaybackFailedEventHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_request_type('AudioPlayer.PlaybackFailed')(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        logger.debug('In PlaybackFailedHandler')
        current_track = play_queue.get_current_track()
        song_id = current_track.id
        logger.error(f'Playback Failed: {handler_input.request_envelope.request.error}')
        logger.error(f'Failed playing track with ID: {song_id}')
        track_details = play_queue.get_next_track()
        track_details.offset = 0
        return controller.start_playback('play', None, None, track_details, handler_input)


#
# Exception Handlers
#


class SystemExceptionHandler(AbstractExceptionHandler):
    def can_handle(self, handler_input: HandlerInput, exception: Exception) -> bool:
        return is_request_type('System.ExceptionEncountered')(handler_input)

    def handle(self, handler_input: HandlerInput, exception: Exception) -> Response:
        logger.debug('In SystemExceptionHandler')
        logger.error(f'System Exception: {exception}')
        logger.error(f'Request Type Was: {get_request_type(handler_input)}')
        error = handler_input.request_envelope.request.to_dict()
        logger.error(f"Details: {error.get('error').get('message')}")

        if get_request_type(handler_input) == 'IntentRequest':
            logger.error(f'Intent Name Was: {get_intent_name(handler_input)}')

        speech = sanitise_speech_output("Entschuldigung, ich habe das nicht verstanden. Kannst du es bitte wiederholen?")
        handler_input.response_builder.speak(speech).ask(speech)

        return handler_input.response_builder.response


class GeneralExceptionHandler(AbstractExceptionHandler):
    def can_handle(self, handler_input: HandlerInput, exception: Exception) -> bool:
        return True

    def handle(self, handler_input: HandlerInput, exception: Exception) -> Response:
        logger.debug('In GeneralExceptionHandler')
        logger.error(f'General Exception: {exception}')
        logger.error(f'Request Type Was: {get_request_type(handler_input)}')

        if get_request_type(handler_input) == 'IntentRequest':
            logger.error(f'Intent Name Was: {get_intent_name(handler_input)}')

        speech = sanitise_speech_output("Entschuldigung, ich habe das nicht verstanden. Kannst du es bitte wiederholen?")
        handler_input.response_builder.speak(speech).ask(speech)

        return handler_input.response_builder.response


#
# Request Interceptors
#


class LoggingRequestInterceptor(AbstractRequestInterceptor):
    def process(self, handler_input: HandlerInput):
        logger.debug(f'Request received: {handler_input.request_envelope.request}')


class LoggingResponseInterceptor(AbstractResponseInterceptor):
    def process(self, handler_input: HandlerInput, response: Response):
        logger.debug(f'Response sent: {response}')

#
# Functions
#


def sanitise_speech_output(speech_string: str) -> str:
    logger.debug('In sanitise_speech_output()')

    if '&' in speech_string:
        speech_string = speech_string.replace('&', 'und')
    if '/' in speech_string:
        speech_string = speech_string.replace('/', 'und')
    if '\\' in speech_string:
        speech_string = speech_string.replace('\\', 'und')
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
    sb.add_global_request_interceptor(LoggingRequestInterceptor())
    sb.add_global_response_interceptor(LoggingResponseInterceptor())

sa = SkillAdapter(skill=sb.create(), skill_id='test', app=app)
sa.register(app=app, route='/')

if navidrome_log_level == 3:
    logger.warning('AskNavidrome debugging has been enabled!')

    @app.route('/queue')
    def view_queue():
        current_track = play_queue.get_current_track()
        return render_template('table.html', title='AskNavidrome - Queued Tracks',
                               tracks=play_queue.get_current_queue(), current=current_track)

    @app.route('/history')
    def view_history():
        current_track = play_queue.get_current_track()
        return render_template('table.html', title='AskNavidrome - Track History',
                               tracks=play_queue.get_history(), current=current_track)

    @app.route('/buffer')
    def view_buffer():
        current_track = play_queue.get_current_track()
        return render_template('table.html', title='AskNavidrome - Buffered Tracks',
                               tracks=play_queue.get_buffer(), current=current_track)


if __name__ == '__main__':
    app.run(host='0.0.0.0')

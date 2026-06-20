import logging
from typing import Union

from rapidfuzz import fuzz, process


logger = logging.getLogger(__name__)


class CatalogCache:
    """Lazily fetches and caches artist and genre lists from the Subsonic server."""

    def __init__(self, connection) -> None:
        self._connection = connection
        self._artists = None
        self._genres = None

    def get_artists(self) -> list:
        if self._artists is None:
            self._artists = self._fetch_all_artists()
        return self._artists

    def get_genres(self) -> list:
        if self._genres is None:
            self._genres = self._fetch_all_genres()
        return self._genres

    def refresh(self) -> None:
        self._artists = None
        self._genres = None

    def _fetch_all_artists(self) -> list:
        """Flatten the alphabetical index structure from getArtists() into a simple list."""
        try:
            response = self._connection.conn.getArtists()
            index_list = response.get('artists', {}).get('index', [])

            artists = []
            for index in index_list:
                for artist in index.get('artist', []):
                    artists.append({'id': artist.get('id'), 'name': artist.get('name', '')})

            logger.debug(f'Cached {len(artists)} artists from server')
            return artists
        except Exception:
            logger.error('Failed to fetch artist catalog', exc_info=True)
            return []

    def _fetch_all_genres(self) -> list:
        """Fetch the genre list from the server."""
        try:
            response = self._connection.conn.getGenres()
            genre_list = response.get('genres', {}).get('genre', [])

            genres = [g.get('value', '') for g in genre_list if g.get('value')]
            logger.debug(f'Cached {len(genres)} genres from server')
            return genres
        except Exception:
            logger.error('Failed to fetch genre catalog', exc_info=True)
            return []


def fuzzy_find_artist(catalog: CatalogCache, query: str, threshold: int = 70) -> Union[dict, None]:
    """Find the best matching artist from the cached catalog.

    :param catalog: A CatalogCache instance
    :param query: The artist name to search for
    :param threshold: Minimum score (0-100) to accept a match
    :return: The matched artist dict {id, name} or None
    """
    artists = catalog.get_artists()
    if not artists:
        return None

    choices = {artist['name']: artist for artist in artists if artist.get('name')}

    result = process.extractOne(
        query, choices.keys(), scorer=fuzz.token_sort_ratio, score_cutoff=threshold
    )

    if result is None:
        logger.debug(f'Fuzzy artist search: no match for "{query}" above threshold {threshold}')
        return None

    matched_name, score, _ = result
    logger.info(f'Fuzzy artist match: "{query}" → "{matched_name}" (score: {score})')
    return choices[matched_name]


def fuzzy_find_album(albums: list, query: str, threshold: int = 70) -> Union[dict, None]:
    """Find the best matching album from a list of album dicts.

    :param albums: A list of album dicts (each must have a 'name' key)
    :param query: The album name to search for
    :param threshold: Minimum score (0-100) to accept a match
    :return: The matched album dict or None
    """
    if not albums:
        return None

    choices = {album.get('name', ''): album for album in albums if album.get('name')}

    result = process.extractOne(
        query, choices.keys(), scorer=fuzz.token_sort_ratio, score_cutoff=threshold
    )

    if result is None:
        logger.debug(f'Fuzzy album search: no match for "{query}" above threshold {threshold}')
        return None

    matched_name, score, _ = result
    logger.info(f'Fuzzy album match: "{query}" → "{matched_name}" (score: {score})')
    return choices[matched_name]


def fuzzy_find_genre(catalog: CatalogCache, query: str, threshold: int = 70) -> Union[str, None]:
    """Find the best matching genre from the cached catalog.

    :param catalog: A CatalogCache instance
    :param query: The genre name to search for
    :param threshold: Minimum score (0-100) to accept a match
    :return: The matched genre string or None
    """
    genres = catalog.get_genres()
    if not genres:
        return None

    result = process.extractOne(
        query, genres, scorer=fuzz.token_sort_ratio, score_cutoff=threshold
    )

    if result is None:
        logger.debug(f'Fuzzy genre search: no match for "{query}" above threshold {threshold}')
        return None

    matched_name, score, _ = result
    logger.info(f'Fuzzy genre match: "{query}" → "{matched_name}" (score: {score})')
    return matched_name


def fuzzy_find_playlist(playlists: list, query: str, threshold: int = 70) -> Union[str, None]:
    """Find the best matching playlist from a list of playlist dicts.

    :param playlists: A list of playlist dicts (each must have 'id' and 'name' keys)
    :param query: The playlist name to search for
    :param threshold: Minimum score (0-100) to accept a match
    :return: The matched playlist ID or None
    """
    if not playlists:
        return None

    choices = {}
    for pl in playlists:
        name = pl.get('name', '')
        if name:
            choices[name] = pl.get('id')

    result = process.extractOne(
        query, choices.keys(), scorer=fuzz.token_sort_ratio, score_cutoff=threshold
    )

    if result is None:
        logger.debug(f'Fuzzy playlist search: no match for "{query}" above threshold {threshold}')
        return None

    matched_name, score, _ = result
    logger.info(f'Fuzzy playlist match: "{query}" → "{matched_name}" (score: {score})')
    return choices[matched_name]

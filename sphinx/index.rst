.. AskNavidrome documentation master file, created by
   sphinx-quickstart on Sat Jul  2 13:52:30 2022.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

**AskNavidrome Alexa Skill Documentation**
==========================================

**AskNavidrome** is an Alexa skill which allows you to play music hosted on a SubSonic API compatible media server, like Navidrome.

This allows to you stream your own music collection to your Echo devices without the restrictions you would normally face with regular 
streaming services like Amazon Music or Spotify.  AskNavidrome allows you to:

- Skip backwards and forwards in your current queue or playlist without limitation.
- Avoid paying subscription costs.
- Avoid being forced to listen to adverts at regular intervals.
- Actually use the music collection you have already paid for!
- Run the service on a PC directly or inside a Docker container.

This skill was inspired by `AskSonic <https://github.com/srichter/asksonic>`_, however AskSonic was missing two features I required,
the ability to play playlists and the ability to play an individual song.  Instead of contributing to that project I have opted to
create a new skill based on the **Alexa Skills Kit SDK for Python** as this has been updated more recently than *flask-ask* which is used 
by AskSonic, AskNavidrome is not a replacement for AskSonic and it does not implement all of AskSonic's features, it is however a viable
alternative for those that would like a simple skill to let you stream your own music collection.

.. warning:: 
   The skill requires a username and password for your Navidrome installation which is stored in clear text.  As the web service needs to be 
   publicly accessible there is a chance that this password could be compromised.  Please do not use an administrative account for your 
   Navidrome installation or a password that you use on any other service.  This software is distributed under the MIT license and no warranty
   is provided.


Requirements
************

In order to use AskNavidrome you will need:

**Your Music Collection**

Your collection needs to have been converted to a digital format like MP3.  There are many tutorials available on the web to help you do this, but do 
be aware that there are limitations on the types of files that Echo devices can stream. You should review these before converting your collection as if
you do not meet the requirements they will need to be transcoded before your Echo device can stream them. This article explains `Amazon's
Audio Stream Requirements <https://developer.amazon.com/en-US/docs/alexa/custom-skills/audioplayer-interface-reference.html#audio-stream-requirements>`_

**A SubSonic API Compatible Media Server**

I use Navidrome, but you can use any flavour of SubSonic that you like.  For information on getting and setting up Navidrome
check out their website `Navidrome <https://www.navidrome.org/>`_.  Your media server must be available on port 443 and serve requests using
https with a valid TLS certificate, these are requirements dictated by Amazon and you must meet them or you will be unable to stream your collection.
The media server needs to be publicly accessible from the Internet, in addition to allowing you to use this skill you will then be able to use any
SubSonic API compatible mobile app to listen to your collection too.

You can get free TLS certificates from `Let's Encrypt <https://letsencrypt.org/>`_

You can set up dynamic DNS to make your media server accessible for free with `afraid.org <https://freedns.afraid.org/>`_

**Tags**

This may seem obvious but you need to make sure that your collection is accurately tagged with information like the artist, title, track number etc.
as this is the only way that your media server can identify the music in your collection.  If you need a tool to help with this have a look at
`MusicBrainz Picard <https://picard.musicbrainz.org/>`_.

**An Amazon Echo Device**

You need something to listen to your music on!


About the AskNavidrome Skill
****************************

.. image:: resources/AskNavidrome_Diagram.png
  :width: 800
  :align: center
  :alt: AskNavidrome Overview Diagram

The skill consists of two parts, the actual Alexa skill and the web service service which allows the skill to connect to your SubSonic API 
compatible media server.  The web service needs to have a valid TLS certificate, the easiest way to enable this is to run the web service
behind a reverse proxy, the web service also needs to be publicly accessible on the Internet to allow the Alexa skill to access the service.


Supported Intents
*****************

+-------------------------------------------+--------------------------------------------+-------------------------------------+
| Intent Name                               | Description                                | Example                             |
+===========================================+============================================+=====================================+
| :class:`~app.NaviSonicPlayMusicByArtist`  | Play music by a specific artist            | Play Where is my Mind by The Pixies |
+-------------------------------------------+--------------------------------------------+-------------------------------------+
| :class:`~app.NaviSonicPlayAlbumByArtist`  | Play a specific album by a specific artist | Play The Blue Album by The Beatles  |
+-------------------------------------------+--------------------------------------------+-------------------------------------+
| :class:`~app.NaviSonicPlaySongByArtist`   | Play a specific song by a specific artist  | Play the song Help by The Beatles   |
+-------------------------------------------+--------------------------------------------+-------------------------------------+
| :class:`~app.NaviSonicPlayPlaylist`       | Play a playlist                            | Play the playlist work music        |
+-------------------------------------------+--------------------------------------------+-------------------------------------+
| :class:`~app.NaviSonicPlayMusicByGenre`   | Play music with a specific genre           | Play jazz music                     |
+-------------------------------------------+--------------------------------------------+-------------------------------------+
| :class:`~app.NaviSonicPlayMusicRandom`    | Play a random mix of songs                 | Play random songs                   |
+-------------------------------------------+--------------------------------------------+-------------------------------------+
| :class:`~app.NaviSonicPlayFavouriteSongs` | Play your starred / favourite songs        | Play my favourite songs             |
+-------------------------------------------+--------------------------------------------+-------------------------------------+
| :class:`~app.NaviSonicRandomiseQueue`     | Shuffle / randomise the current play queue | Shuffle the queue                   |
+-------------------------------------------+--------------------------------------------+-------------------------------------+
| :class:`~app.NaviSonicSongDetails`        | Give details on the playing track          | What is playing                     |
+-------------------------------------------+--------------------------------------------+-------------------------------------+
| :class:`~app.NaviSonicStarSong`           | Star / favourite a song                    | Star this song                      |
+-------------------------------------------+--------------------------------------------+-------------------------------------+
| :class:`~app.NaviSonicUnstarSong`         | Unstar / unfavourite a song                | Unstar this song                    |
+-------------------------------------------+--------------------------------------------+-------------------------------------+

The following control intents are also supported:

- :class:`Next / Skip <app.NextPlaybackHandler>`
- :class:`Previous / Back <app.PreviousPlaybackHandler>`
- :class:`Pause <app.PausePlaybackHandler>`
- :class:`Resume <app.ResumePlaybackHandler>`

Due to the way that Alexa skills operate there are some limitations.  Full music Alexa skills require a catalog of content to be provided and this defeats
the purpose of being able to search and stream from your own server directly.  Because of this a custom skill type is used along with the AudioPlayer interface,
but this has some limitations in how the skill is invoked.

The following voice commands should be successful (thanks to Raul824)

- Alexa ask Navisonic What is Playing?
- Alexa ask Navisonic to star this song.
- Alexa ask Navisonic to unstar this song.
- Alexa ask Navisonic to play rock music
- Alexa ask Navisonic to play playlist "Playlist Name"

If you have any problems with these, you can open the skill manually with *Alexa, open Navisonic*. Similarly this can be done when a track is playing, for example
if you want to get information on the track that is playing you will need to invoke the skill and call the intent by saying the following while the track is playing:

- Alexa, open Navisonic
- What is playing?


Installation and Setup
**********************

Creating the AskNavidrome Alexa Skill 
-------------------------------------

#. Login to the Amazon Alexa Skills Kit Builder at https://developer.amazon.com.
   - You must use the same account that is set on your Echo devices.
#. Click *Create Skill*
#. Configure the skill:

   .. image:: resources/create_skill_1.png
      :width: 800
      :align: center
      :alt: Skill Creation Step 1
       

   - Set *Skill name* to the name you wish to use to invoke the skill.  This should be two words or a warning will be raised, I have found that a single word
     still works when testing.  It can be hard to find a good skill name so feel free to experiment!
   - Set *Primary locale* to your locale, this **must** also be the locale set on your Echo device.
     
     .. note:: The locale setting is extremely important, if the skill locale and the locale set on your Echo device do not match the skill will not work.  In
      addition there are no error messages generated making the issue quite difficult to troubleshoot.  The locale on your Echo device can be set via the Alexa Android
      app.  Please do check the locale setting if you have trouble setting up the skill as the Alexa Skill Builder will default to your local locale, but Echo devices
      are set to the US locale by default.  Checking this first will save you a few hours of troubleshooting!

   - Set sync locales to *No*
   - Choose *Custom* as the model.
   - Choose *Provision your own* as the hosting method for backend resources.
   - Click *Create skill* again

#. Choose the template

   .. image:: resources/create_skill_2.png
      :width: 800
      :align: center
      :alt: Skill Creation Step 2

   - Choose *Start from Scratch*
   - Click *Continue with template* and wait while the skill is created.

#. Upload the intents

   .. image:: resources/create_skill_3.png
      :width: 800
      :align: center
      :alt: Skill Creation Step 3

   - Click *Interaction Model*, then *JSON Editor*
   - Delete everything that is currently in the editor and paste in the contents of **alexa.json**
   - Click *Save Model*

#. Configure playlists

   To be able to play your playlists you must add the name of each playlist to the *playlist_names* slot type.  
   You will need to maintain the list and add additional playlist names as you create them to allow them to
   be played via the AskNavisonic skill.

   .. image:: resources/create_skill_4.png
      :width: 800
      :align: center
      :alt: Skill Creation Step 4

   - Click *Slot Types*.
   - Click *playlist_names*.
   - Add and remove names as required.
   - Click the *Save Model* button when you are done.

#. Enable the Audio Player interface

   .. image:: resources/create_skill_5.png
      :width: 800
      :align: center
      :alt: Skill Creation Step 5

   - Click *Interfaces*, enable *Audio Player*, then click *Save Interfaces*

#. Set the endpoint

   The skill's endpoint is the location of the AskNavidrome web service.

   .. image:: resources/create_skill_6.png
      :width: 800
      :align: center
      :alt: Skill Creation Step 6

   - Click *Endpoint*
   - Select *HTTPS*
   - Enter the the URL to the web service in the *Default Region* box.
   - Select the SSL certificate type.  This will depend on your setup, if you are using Let's Encrypt
     choose *My development endpoints has a certificate from a trusted certificate authority*
   - Click *Save Endpoints*

#. Build the skill

   .. image:: resources/create_skill_7.png
      :width: 800
      :align: center
      :alt: Skill Creation Step 7

   - Click *Invocations*, *Skill Invocation Name*.
   - Click *Save Model*.
   - Click *Build Model*, the process will take a few minutes.

#. Add the skill to your Echo devices.

   The skill you just created should now be available as a development skill in your Alexa app, you can add the development skill to your
   Echo devices.

   .. warning:: It is important that you **do not** publish the skill.  If you do anyone that uses the skill will be able to stream your music
      collection, it may also be possible for credentials to be retrieved.
   

Deploying the AskNavidrome Web Service
--------------------------------------

The AskNavidrome Web Service is written in Python and can be run directly on a PC with a Python installation, or as a Docker container (recommended).  
Whichever method you use, the service and your Navidrome installation must be available via HTTPS with a well known certificate.  One of the easiest 
ways to implement this is with a reverse proxy.  There are several 
available for free:

* `Caddy <https://caddyserver.com/>`_.
* `Apache <https://httpd.apache.org/docs/2.4/howto/reverse_proxy.html/>`_.
* `Nginx <https://docs.nginx.com/nginx/admin-guide/web-server/reverse-proxy/>`_.


Run on your PC
~~~~~~~~~~~~~~

Please remember that the web service needs to be publicly accessible, if you are running it directly on your PC this means your PC is publicly
accessible.

#. Install Python 3
      * `python3.org <https://www.python.org/downloads/>`_
#. Install git tools
      * `git-scm.com <https://git-scm.com/book/en/v2/Getting-Started-Installing-Git>`_
#. Create a directory for the web service
#. Change to the directory and clone the repository from GitHub

   .. code-block:: bash

      cd directory
      git clone https://github.com/rosskouk/asknavidrome.git


#. Change directory to the skill folder

   .. code-block:: bash
     
      cd asknavidrome/skill

#. Start the skill by setting the required environment variables and executing the application
   you can find details of what each option does in the *configuration* section.

   .. code-block:: bash

      NAVI_SKILL_ID=<your-skill-id> \
      NAVI_SONG_COUNT=50 \
      NAVI_URL=https://your-navidrome-server.test \
      NAVI_USER=<username> \
      NAVI_PASS=<password> \
      NAVI_PORT=443 \
      NAVI_API_PATH=/rest \
      NAVI_API_VER=1.16.1 \
      NAVI_DEBUG=0 \
      python3 app.py


Run inside a Docker container
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A Dockerfile has been provided and a prebuilt container is hosted on github.com. **Please note that the prebuilt container was created on an amd64 platform**.  If you
require a different architecture such as arm for a Raspberry Pi, you will need to build a new image using the Dockerfile provided with the repository.

You can configure the service by passing environment variables to the *docker run* command.

.. code-block:: bash
   
   docker run -p 5000:5000 \ 
   -e NAVI_SKILL_ID=<your-skill-id> \
   -e NAVI_SONG_COUNT=50 \
   -e NAVI_URL=https://your-navidrome-server.test \
   -e NAVI_USER=<username> \
   -e NAVI_PASS=<password> \
   -e NAVI_PORT=443 \
   -e NAVI_API_PATH=/rest \
   -e NAVI_API_VER=1.16.1 \
   -e NAVI_DEBUG=0 \
   ghcr.io/rosskouk/asknavidrome:<tag>

If you intent to use the container to build a Kubernetes pod, I have created a side car container which can automatically configure and renew 
TLS certificates with the Kubernetes Nginx Ingress.  `More information <https://github.com/rosskouk/docker-image-k8s-letsencrypt>`_.


Configuration
~~~~~~~~~~~~~

The AskNavidrome Web Service reads it's configuration from environment variables and needs the following configuration 
information to run:

+----------------------+----------------------------------------------------------------+------------------------------------------------------+
| Environment Variable | Description                                                    | Example                                              |
+======================+================================================================+======================================================+
| NAVI_SKILL_ID        | The ID of your Alexa skill, this prevents other skills from    | amzn1.ask.skill.xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx |
|                      | connecting to the web service.                                 |                                                      |
+----------------------+----------------------------------------------------------------+------------------------------------------------------+
| NAVI_SONG_COUNT      | The minimum number of songs to add to a playlist.  If playing  | 50                                                   |
|                      | random music, music by genre or music by an artist the web     |                                                      |
|                      | service will ensure the minimum number of tracks added to the  |                                                      |
|                      | queue is at least this value                                   |                                                      |
+----------------------+----------------------------------------------------------------+------------------------------------------------------+
| NAVI_URL             | The URL to the Subsonic API server                             | ``https://navidrome.example.test``                   |
+----------------------+----------------------------------------------------------------+------------------------------------------------------+
| NAVI_USER            | The user name used to connect to the Subsonic API server       | bob                                                  |
+----------------------+----------------------------------------------------------------+------------------------------------------------------+
| NAVI_PASS            | The password used to connect to the Subsonic API server        | ``Sup3rStrongP@ssword``                              |
+----------------------+----------------------------------------------------------------+------------------------------------------------------+
| NAVI_PORT            | The port the Subsonic API server is listening on               | 443                                                  |
+----------------------+----------------------------------------------------------------+------------------------------------------------------+
| NAVI_API_PATH        | The path to the Subsonic API, this should be /rest if you are  | /rest                                                |
|                      | using Navidrome and haven't changed anything                   |                                                      |
+----------------------+----------------------------------------------------------------+------------------------------------------------------+
| NAVI_API_VER         | The version of the Subsonic API in use                         | 1.16.1                                               |
+----------------------+----------------------------------------------------------------+------------------------------------------------------+
| NAVI_DEBUG           | Enable debugging, to disable to not set this variable          | 1                                                    |
+----------------------+----------------------------------------------------------------+------------------------------------------------------+


Troubleshooting
***************

Troubleshooting and debugging Alexa skills can be a little frustrating, here are the best ways I have found to do it.

#. Understand that the Alexa skill is effectively just a set of buttons.
   All the skill does is call functions in the web service, it does nothing other than translate what you say to the function name that will perform the task.
   Very little can go wrong with this, but here is a list of things to check:

   * Does the locale of the skill match the locale on your Echo device?  If this is mismatched it looks like nothing happens when you try to invoke the skill.
   * Is the endpoint set correctly?  The endpoint is the URL to the web service, if the skill cannot communicate with the web service check this first.
     you must ensure that the URL is https and the certificate is compatible with Amazon services.
   * If an intent does not work, you might need to add an additional phrase to the intent in the developer console.  The included phrases work for me, you might
     want to make some changes though.

#. Enable debugging and look at the logs generated by the web service.

#. When debugging is enabled the following web pages are available from the web service

   * url-to-web-service/queue

     * Shows the tracks in the current queue

   * url-to-web-service/history

     * Shows the tracks that have already been played

   * url-to-web-service/buffer

     * Shows the tracks in the buffer.  Note that the buffer and queue differ as Amazon will request the next track to be queued before the track playing is
       finished.  The buffer can be thought of as the list of tracks still to be sent to Amazon, where as the queue is the list of tracks still to be played.

#. Use the test page in the developer console
   The test page will show you the responses between Amazon and an simulated Echo device, this can help you uncover error messages that are normally hidden.

   .. image:: resources/debugging_1.png
      :width: 800
      :align: center
      :alt: debugging Step 1

   * Click test and make sure you tick **Device Log**
   * You can type instructions in the box or use the microphone on your device

   .. image:: resources/debugging_2.png
      :width: 800
      :align: center
      :alt: debugging Step 2

   * After you have entered a command you will get the Alexa response back, scroll down to the **Device Log** section and click through the entries
     the entries will contain any errors that were thrown.

Known Issues
------------

#. The skill appears to work but no music is played.  Errors similar to below appear in the web service log

   .. code-block:: bash

      2022-11-19 13:16:45,478 - root - DEBUG - In PlaybackFailedHandler                                                                                                                                               │
      2022-11-19 13:16:45,479 - root - ERROR - Playback Failed: {'message': 'Device playback error', 'object_type': 'MEDIA_ERROR_UNKNOWN'}                                                                            │
      2022-11-19 13:16:45,480 - werkzeug - INFO - 10.44.17.62 - - [19/Nov/2022 13:16:45] "POST / HTTP/1.1" 200 -                                                                                                      │
      2022-11-19 13:16:48,599 - root - DEBUG - In PlaybackFailedHandler                                                                                                                                               │
      2022-11-19 13:16:48,600 - root - ERROR - Playback Failed: {'message': 'Device playback error','object_type': 'MEDIA_ERROR_INTERNAL_DEVICE_ERROR'}

   * I have not found a reason as to why this happens from time to time, however it can be resolved by doing a hard reboot of your Echo device.  
     Disconnect the power for a minute and plug it back in then try again and music should play

#. The following error is displayed when you try to run the Docker container

   .. code-block:: bash

      exec /opt/env/bin/python3: exec format error

   * You are using the prebuilt container on a non amd64 based system.  You will need to build your own Docker image using the Dockerfile included
     with the repository.

Code Documentation
******************

.. toctree::
   :maxdepth: 1
   :caption: Contents:

AskNavidrome main
-----------------
.. automodule:: app
   :members:
   :undoc-members:

AskNavidrome controller
-----------------------
.. automodule:: asknavidrome.controller
   :members:
   :undoc-members:

AskNavidrome media queue
------------------------
.. autoclass:: asknavidrome.media_queue.MediaQueue
   :members:
   :undoc-members:

AskNavidrome subsonic API
-------------------------
.. autoclass:: asknavidrome.subsonic_api.SubsonicConnection
   :members:
   :undoc-members:

AskNavidrome track
------------------
.. autoclass:: asknavidrome.track.Track
   :members:
   :undoc-members:

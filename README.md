# Voice-Activated Library

The Week 4 library app (Flask REST API + static frontend) with a voice layer
on top. Speak one sentence, it becomes **one real HTTP request** to the
library API, and a librarian voice reads out the result.

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then put your Azure SPEECH_KEY and SPEECH_REGION in .env
python app.py
```

Open http://localhost:5001 in Chrome or Firefox, click 🎤, speak, click 🎤 again.
No system ffmpeg is needed: `imageio-ffmpeg` brings its own binary.

## Tests

```bash
python test_voice_commands.py   # sentence -> command parser
python test_endpoints.py        # every endpoint once, with Flask's test client
```

Neither test calls Azure.

## How a voice command works

1. The browser records with `MediaRecorder` and uploads the WebM to `POST /api/voice/recognize`.
2. The server converts it to 16 kHz mono WAV (imageio-ffmpeg) and Azure speech-to-text
   returns the sentence (a `PhraseListGrammar` helps with command words and titles).
3. `POST /api/voice/parse` runs `voice_commands.parse(text)` →
   `{"method": "POST", "path": "/api/items/3/checkout", "body": null}`.
4. The frontend sends that request with `fetch` to the normal library endpoint.
5. The real status + JSON is turned into a librarian sentence, which `POST /api/speak`
   synthesizes with Azure (cached on the server). Nothing is spoken while recording.
6. The voice log shows heard text → request → status → reply, and the item cards refresh.

The text box under the microphone sends typed text through the same steps 3–6.

## Example commands

| Say | Request |
| --- | --- |
| Create item, type book, title The Catcher in the Rye, author J.D. Salinger, pages 220 | `POST /api/items` |
| Create item, type DVD, title Up, author Pete Docter, minutes 96 | `POST /api/items` |
| List all items / list available books / list checked out DVDs | `GET /api/items?available=…&type=…` |
| Show item 3 / get item three | `GET /api/items/3` |
| Replace item 3, title X, author Y, pages 300 | `PUT /api/items/3` |
| Update item 3, pages 250 / change item 3 title to X | `PATCH /api/items/3` |
| Delete item 3 / remove item 3 | `DELETE /api/items/3` |
| Check out item 3 | `POST /api/items/3/checkout` |
| Return item 3 | `POST /api/items/3/return` |

Item numbers can be digits, words ("item three"), "item number 3", or the
homophones Azure sometimes writes: "to/too" = 2, "for" = 4, "won" = 1.

Known limit: a title that contains a field word (e.g. "title The Lost Pages")
is split at that word, because the field words are how the parser finds the values.

## Files

- `app.py` – the 8 library endpoints (unchanged) + 3 voice routes
- `custom_classes.py` – library model (unchanged)
- `voice_commands.py` – `parse(text)`: sentence → `{method, path, body}` or `{error}`
- `static/script.js` – item cards, form, filters (unchanged)
- `static/voice.js` – recording, voice log, librarian replies, speech playback

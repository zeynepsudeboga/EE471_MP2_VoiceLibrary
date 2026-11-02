"""JSON REST API for the library. Routes only translate HTTP into
LibraryCollection method calls; the rules live in custom_classes.py.

The voice routes at the bottom are an extra layer: they turn speech into
text, text into a command, and text into speech. The command itself is sent
by the frontend to the normal /api/items endpoints."""

import os
import subprocess
import tempfile
import threading
from pathlib import Path

import azure.cognitiveservices.speech as speechsdk
import imageio_ffmpeg
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request
from werkzeug.exceptions import HTTPException

from custom_classes import (
    Book,
    DVD,
    LibraryCollection,
    ItemNotFoundError,
    ItemStateError,
)
import voice_commands

# .env sits next to this file, so it is found no matter where the app is started from.
load_dotenv(Path(__file__).resolve().parent / ".env")
SPEECH_KEY = os.getenv("SPEECH_KEY")
SPEECH_REGION = os.getenv("SPEECH_REGION")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB upload limit (recordings)

ITEM_CLASSES = {"book": Book, "dvd": DVD}

library = LibraryCollection()
library.add_item(Book("Dune", "Frank Herbert", 412))
library.add_item(Book("1984", "George Orwell", 328))
library.add_item(DVD("The Matrix", "Wachowski Sisters", 136))
library.add_item(DVD("Interstellar", "Christopher Nolan", 169))


# --- Error handlers: exceptions from custom_classes become JSON errors ---

def error_response(message, status):
    return jsonify({"error": str(message)}), status


@app.errorhandler(ItemNotFoundError)
def handle_not_found(error):
    return error_response(error, 404)


@app.errorhandler(ItemStateError)
def handle_state_error(error):
    return error_response(error, 409)


@app.errorhandler(ValueError)
@app.errorhandler(TypeError)
def handle_bad_input(error):
    return error_response(error, 400)


@app.errorhandler(HTTPException)
def handle_http_error(error):
    # Unknown URLs, wrong methods, etc. also answer with JSON.
    return error_response(error.description, error.code)


# --- Input helpers: only check basic types, not library rules ---

def read_json_body():
    """Return the request body as a dict, or raise ValueError."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError("Request body must be a JSON object.")
    return data


def check_field_types(data):
    """Raise ValueError if a known field has the wrong type.

    Unknown field names are left to update_item(), which decides what is editable.
    """
    for name in ("title", "author"):
        if name in data and (not isinstance(data[name], str) or not data[name].strip()):
            raise ValueError(f"'{name}' must be a non-empty string.")
    for name in ("page_count", "duration"):
        if name in data:
            value = data[name]
            # bool is a subclass of int in Python, so exclude it explicitly.
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"'{name}' must be a positive integer.")


def parse_bool(value, name):
    if value == "true":
        return True
    if value == "false":
        return False
    raise ValueError(f"'{name}' must be 'true' or 'false'.")


# --- Routes ---

@app.get("/")
def index():
    # The frontend is plain static files; Flask serves them from static/.
    return app.send_static_file("index.html")


@app.post("/api/items")
def create_item():
    data = read_json_body()
    item_class = ITEM_CLASSES.get(data.get("type"))
    if item_class is None:
        raise ValueError("'type' must be 'book' or 'dvd'.")

    fields = {name: value for name, value in data.items() if name != "type"}
    missing = [name for name in item_class.EDITABLE_FIELDS if name not in fields]
    if missing:
        raise ValueError(f"Missing fields: {', '.join(missing)}.")
    unknown = [name for name in fields if name not in item_class.EDITABLE_FIELDS]
    if unknown:
        raise ValueError(f"Unknown fields: {', '.join(unknown)}.")
    check_field_types(fields)

    item = item_class(**fields)
    library.add_item(item)
    return jsonify(item.to_dict()), 201


@app.get("/api/items")
def list_items():
    available = request.args.get("available")
    item_type = request.args.get("type")
    if available is not None:
        available = parse_bool(available, "available")
    if item_type is not None and item_type not in ITEM_CLASSES:
        raise ValueError("'type' must be 'book' or 'dvd'.")

    items = library.list_items(available=available, item_type=item_type)
    return jsonify([item.to_dict() for item in items]), 200


@app.get("/api/items/<int:item_id>")
def get_item(item_id):
    return jsonify(library.get_item(item_id).to_dict()), 200


@app.put("/api/items/<int:item_id>")
def replace_item(item_id):
    data = read_json_body()
    item = library.get_item(item_id)
    missing = [name for name in item.EDITABLE_FIELDS if name not in data]
    if missing:
        raise ValueError(f"PUT needs all editable fields. Missing: {', '.join(missing)}.")
    check_field_types(data)
    return jsonify(library.update_item(item_id, **data).to_dict()), 200


@app.patch("/api/items/<int:item_id>")
def update_item(item_id):
    data = read_json_body()
    if not data:
        raise ValueError("Give at least one field to change.")
    check_field_types(data)
    return jsonify(library.update_item(item_id, **data).to_dict()), 200


@app.delete("/api/items/<int:item_id>")
def delete_item(item_id):
    library.remove_item(item_id)
    return "", 204


@app.post("/api/items/<int:item_id>/checkout")
def checkout_item(item_id):
    item = library.get_item(item_id)
    message = item.checkout()
    return jsonify({"item": item.to_dict(), "message": message}), 200


@app.post("/api/items/<int:item_id>/return")
def return_item(item_id):
    item = library.get_item(item_id)
    item.return_item()
    return jsonify(item.to_dict()), 200


# --- Voice layer: speech-to-text, sentence parsing, text-to-speech ---

VOICE = "en-US-AvaNeural"
MAX_SPEAK_LENGTH = 500
ALLOWED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".webm", ".ogg"}

# Words Azure should expect. Short words like "to" or "item" are recognized more reliably.
COMMAND_PHRASES = [
    "item", "item number", "create item", "list", "show item", "get item", "replace item",
    "update item", "change item", "delete item", "remove item", "check out item",
    "return item", "type book", "type DVD", "title", "author", "pages", "minutes",
    "duration", "available", "checked out", "books", "DVDs",
]

speech_cache = {}  # (text, voice) -> WAV bytes, kept in memory while the server runs


def recognition_config():
    """Azure settings from .env. Raises ValueError (-> 400) if they are missing."""
    if not SPEECH_KEY or not SPEECH_REGION:
        raise ValueError("Azure Speech is not configured: add SPEECH_KEY and SPEECH_REGION to .env.")
    return speechsdk.SpeechConfig(subscription=SPEECH_KEY, region=SPEECH_REGION)


def convert_to_wav(src_path, dst_path):
    """Convert any audio file to 16 kHz mono 16-bit PCM WAV, the format the Speech SDK expects."""
    # imageio-ffmpeg ships its own ffmpeg binary, so no system-wide install is needed.
    subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", src_path,
         "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", dst_path],
        check=True,
        capture_output=True,
    )


def recognize(wav_path):
    """Recognize the whole file with continuous recognition.

    Returns (text, cancel_message). cancel_message is set only if Azure canceled with an error.
    """
    config = recognition_config()
    config.speech_recognition_language = "en-US"
    audio_config = speechsdk.audio.AudioConfig(filename=wav_path)
    recognizer = speechsdk.SpeechRecognizer(speech_config=config, audio_config=audio_config)

    # Command words plus the titles and authors in the library help Azure spell them right.
    phrase_list = speechsdk.PhraseListGrammar.from_recognizer(recognizer)
    for phrase in COMMAND_PHRASES:
        phrase_list.addPhrase(phrase)
    for item in library.list_items():
        phrase_list.addPhrase(item.title)
        phrase_list.addPhrase(item.author)

    parts = []
    errors = []
    done = threading.Event()

    def on_recognized(evt):
        if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech and evt.result.text:
            parts.append(evt.result.text)

    def on_canceled(evt):
        # Reaching the end of the file also fires "canceled" with reason EndOfStream; that's not an error.
        if evt.cancellation_details.reason == speechsdk.CancellationReason.Error:
            message = f"Speech recognition canceled: {evt.cancellation_details.reason.name}"
            if evt.cancellation_details.error_details:
                message += f" – {evt.cancellation_details.error_details}"
            errors.append(message)
        done.set()

    recognizer.recognized.connect(on_recognized)
    recognizer.canceled.connect(on_canceled)
    recognizer.session_stopped.connect(lambda evt: done.set())

    recognizer.start_continuous_recognition()
    done.wait(timeout=60)  # safety net so a request can't hang forever
    recognizer.stop_continuous_recognition()

    return " ".join(parts), (errors[0] if errors else None)


@app.post("/api/voice/recognize")
def recognize_speech():
    """Audio file in, recognized text out: {"text": "Check out item 3."}"""
    audio = request.files.get("audio")
    if audio is None or not audio.filename:
        raise ValueError("No audio received.")

    extension = Path(audio.filename).suffix.lower()
    if extension not in ALLOWED_AUDIO_EXTENSIONS:
        raise ValueError("Unsupported audio type.")

    # A temporary folder holds both the upload and the converted WAV and is deleted afterwards.
    with tempfile.TemporaryDirectory() as tmp:
        src_path = os.path.join(tmp, "input" + extension)
        wav_path = os.path.join(tmp, "converted.wav")
        audio.save(src_path)

        if os.path.getsize(src_path) == 0:
            raise ValueError("The recording is empty.")
        try:
            convert_to_wav(src_path, wav_path)
        except subprocess.CalledProcessError:
            raise ValueError("Could not read the recording.")

        text, cancel_message = recognize(wav_path)

    if cancel_message:
        return error_response(cancel_message, 502)
    return jsonify({"text": text}), 200


@app.post("/api/voice/parse")
def parse_sentence():
    """Sentence in, API command out: {"method", "path", "body"}, or 422 if not understood."""
    data = read_json_body()
    result = voice_commands.parse(str(data.get("text", "")))
    if "error" in result:
        return jsonify(result), 422
    return jsonify(result), 200


# Same text-to-speech setup as Week 5 (/api/speak in Week-5-Task-2/app.py).
@app.route("/api/speak", methods=["POST"])
def speak():
    data = request.get_json(silent=True) or {}
    text = str(data.get("text", "")).strip()

    if not text:
        return jsonify({"error": "Nothing to say."}), 400
    if len(text) > MAX_SPEAK_LENGTH:
        return jsonify({"error": f"Text is too long (max {MAX_SPEAK_LENGTH} characters)."}), 400

    # Each text is synthesized by Azure only once while the server runs (saves free-tier requests).
    if (text, VOICE) in speech_cache:
        return Response(speech_cache[(text, VOICE)], mimetype="audio/wav")

    speech_config = speechsdk.SpeechConfig(subscription=SPEECH_KEY, region=SPEECH_REGION)
    speech_config.speech_synthesis_voice_name = VOICE
    speech_config.set_speech_synthesis_output_format(
        speechsdk.SpeechSynthesisOutputFormat.Riff24Khz16BitMonoPcm  # RIFF = WAV with header
    )

    # audio_config=None keeps the audio in memory instead of playing it on the server.
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)
    result = synthesizer.speak_text_async(text).get()

    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        speech_cache[(text, VOICE)] = result.audio_data
        return Response(result.audio_data, mimetype="audio/wav")

    if result.reason == speechsdk.ResultReason.Canceled:
        details = result.cancellation_details
        message = f"Speech synthesis canceled: {details.reason.name}"
        if details.error_details:
            message += f" – {details.error_details}"
        return jsonify({"error": message}), 502

    return jsonify({"error": f"Unexpected synthesis result: {result.reason.name}"}), 502


if __name__ == "__main__":
    app.run(port=5001, debug=True)

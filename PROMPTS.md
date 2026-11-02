# PROMPTS – Mini Project 2: Voice-activated Library App

Tool: Claude Code (Opus 5.5). Starting point: the merged Week 4 library app (first commit).
The full, unedited session is in [`transcripts/claude-code-session.md`](transcripts/claude-code-session.md).
This file lists my prompts word for word, with short notes on why I wrote them this way.

## Prompt 1 – Voice layer
```
This folder is my Week 4 library app (Flask REST API + static frontend). Turn it into a voice-activated library app with Azure Speech. My Azure key is in .env (SPEECH_KEY, SPEECH_REGION) — never read or print .env.

Reuse my working voice pipeline from ~/EE471-week5/Week-5-Task-2 (read app.py and static/script.js there): browser MediaRecorder → WebM converted to 16 kHz mono WAV with imageio-ffmpeg (system ffmpeg is NOT installed) → Azure speech-to-text with a PhraseListGrammar → Azure text-to-speech with a server-side cache, and no speaking while recording.

Requirements:
1. Keep all 8 existing endpoints and their status codes unchanged. Voice is an extra layer on top.
2. Mic button (click to start, click to stop). The spoken sentence is turned into ONE call to a real endpoint, executed by the frontend with fetch, so it is a genuine HTTP request.
3. Put the sentence → command logic in a separate file voice_commands.py with a parse(text) function that returns {method, path, body} or an error message. It must handle:
   - Create: "Create item, type book, title The Catcher in the Rye, author J.D. Salinger, pages 220" (DVD uses "minutes" or "duration") → POST /api/items
   - List: "list all items", "list available books", "list checked out DVDs" → GET /api/items with ?available and ?type
   - Get: "show item 3" / "get item 3" → GET
   - Replace: "replace item 3, title X, author Y, pages 300" → PUT (all fields)
   - Update: "update item 3, pages 250" / "change item 3 title to X" → PATCH (only the given fields)
   - Delete: "delete item 3" / "remove item 3" → DELETE
   - Checkout: "check out item 3" → POST checkout
   - Return: "return item 3" → POST return
   Azure's speech-to-text adds commas/periods, changes capitalization and writes numbers as digits ("item 3", "pages 220"), but sometimes as words ("item three") or homophones ("item to/too" = 2, "for" = 4, "won" = 1). Handle all of these. "item number 3" should also work.
4. After every command, the app speaks a librarian-style sentence built from the REAL response (status + JSON), e.g. "Successfully created book 'The Catcher in the Rye' with ID 5.", "Item 3, '1984', has been checked out." Errors are spoken too: 404 → "Sorry, item 9 does not exist.", 409 checkout → "Sorry, item 3 is already checked out.", 409 return → "...is not checked out.", 409 delete → can't delete a checked-out item, 400 → read the error message. For a list, say how many items and their titles. If the sentence is not understood, say so and give an example command.
5. Add a "Voice log" panel showing for each command: what Azure heard → the HTTP request (method + path + body) → status code → what the librarian said. After each command, refresh the item cards.
6. Also add a small text box that sends typed text through the same parser, as a backup for testing.
7. Write a test script for voice_commands.py with many example sentences (including the messy ones above) and run it until all pass. Also test every endpoint once with Flask's test client.
8. Add requirements.txt, .gitignore (.env, .venv, __pycache__, .DS_Store), .env.example and a short README with run instructions. Load .env from the same folder as app.py.

Keep the code readable — I will have to explain every code block in a video.
```
Why: last week (Week 5) I learned that Azure turns spoken numbers into digits, mishears short words and that system ffmpeg is missing on my Mac, so I listed these up front. The frontend makes the real HTTP call, so every voice command is visibly one endpoint call. The parser is in its own file so it can be tested without a microphone.

## Prompt 2 – Text-to-speech crash
```
Text-to-speech fails in the browser. The voice log works ("list all items" → GET /api/items → 200), but the status line shows "Speech synthesis failed: Canceled – Codec de..." and macOS shows "Python quit unexpectedly".

My Week 5 /api/speak in ~/EE471-week5/Week-5-Task-2/app.py works on this Mac. Make our TTS use exactly the same setup: same output format, same SpeechSynthesizer config (audio_config=None), same cache. Then stop any server you started, run the app yourself on port 5001, call /api/speak with curl for a few librarian sentences, check that you get valid audio back and the server doesn't crash, and stop the server again when done so the port is free.
```
Result: the AI made the speak route identical to Week 5. It also found its own mistake: in the first session it had left a test server running on port 5001 (its kill command didn't match the process), which is why my own `python app.py` first failed with "Address already in use". After this fix, speech worked in the browser.

## Prompt 3 – UX fixes I noticed while testing
```
Two UX fixes:
1. Users can't see item IDs, so they can't know what "item 3" refers to in a voice command. Show the ID on every item card as a clear badge like "#3", before the title. IDs don't shift after a delete, so they must come from the API, not from the card's position.
2. The voice log grows forever. Keep newest on top, show at most the last 10 entries, and add a small "Clear" button to the log header.
Don't change any endpoint or the parser. Run both test scripts again, and stop any server you start.
```
Why: a voice app is useless if the user can't see which number to say.

## Prompt 4 – Commits
```
Commit everything in a few logical commits (the .env and .venv must not be committed — verify with git status). Don't push.
```
The AI made the first commit the original Week 4 app, so the later commits show only the voice changes.

## Known limits
- A title that contains a field word (e.g. "The Lost Pages") is cut at that word by the parser.
- Items are kept in memory: restarting the server resets the library to the 4 seeded items.

// Voice layer for the library. One sentence (spoken or typed) becomes ONE
// real HTTP request to the library API. The real answer (status + JSON) is
// turned into a librarian-style sentence, spoken out loud and written to the
// voice log. loadItems() comes from script.js and refreshes the item cards.

const micButton = document.getElementById("mic");
const voiceStatus = document.getElementById("voice-status");
const textCommandForm = document.getElementById("text-command-form");
const textCommandInput = document.getElementById("text-command");
const voiceLog = document.getElementById("voice-log");
const clearLogButton = document.getElementById("clear-log");

const MAX_SPOKEN_TITLES = 10;  // a long list is cut off as "... and 5 more"
const MAX_LOG_ENTRIES = 10;    // the voice log keeps only the newest entries

const STATUS_TEXT = {
    200: "OK", 201: "Created", 204: "No Content",
    400: "Bad Request", 404: "Not Found", 409: "Conflict",
};


// ---------- Sentence -> command -> real request -> librarian reply ----------

// Send one request and return { status, data }. data is the JSON body, or null
// (204 No Content has no body). Unlike request() in script.js this does not
// throw on 4xx, because the librarian needs the status code to answer.
async function callApi(method, path, body = null) {
    const options = { method };
    if (body !== null) {
        options.headers = { "Content-Type": "application/json" };
        options.body = JSON.stringify(body);
    }
    const response = await fetch(path, options);
    const data = response.status === 204 ? null : await response.json().catch(() => null);
    return { status: response.status, data };
}

// The whole voice pipeline for one sentence. source is "voice" or "typed".
async function handleSentence(text, source) {
    const log = { source, heard: text, command: null, status: null, reply: "" };
    try {
        // 1. voice_commands.parse() on the server turns the sentence into a command.
        const parsed = await callApi("POST", "/api/voice/parse", { text });
        if (parsed.status !== 200) {
            log.reply = parsed.data.error;  // "Sorry, I didn't understand ... Try saying ..."
        } else {
            // 2. Send the command as a genuine HTTP request to the library API.
            log.command = parsed.data;
            const { method, path, body } = log.command;
            const answer = await callApi(method, path, body);
            log.status = answer.status;
            // 3. Build the librarian's sentence from the real answer.
            log.reply = librarianReply(log.command, answer.status, answer.data);
        }
    } catch (err) {
        log.reply = "Sorry, I could not reach the library server.";
    }

    addLogEntry(log);
    setStatus(log.reply);
    speak(log.reply);
    await loadItems();  // refresh the item cards
}


// ---------- Librarian replies ----------

// Which of the 8 endpoints was called, read from the method and path.
function actionOf(command) {
    const { method, path } = command;
    if (path.endsWith("/checkout")) return "checkout";
    if (path.endsWith("/return")) return "return";
    if (method === "POST") return "create";
    if (method === "PUT") return "replace";
    if (method === "PATCH") return "update";
    if (method === "DELETE") return "delete";
    return /\/api\/items\/\d+$/.test(path) ? "get" : "list";
}

// The item id in "/api/items/3/checkout" -> 3, or null for create/list.
function itemIdOf(command) {
    const match = command.path.match(/\/api\/items\/(\d+)/);
    return match ? Number(match[1]) : null;
}

function typeName(item) {
    return item.type === "dvd" ? "DVD" : "book";
}

// "the book '1984' by George Orwell, 328 pages"
function describeItem(item) {
    const extra = item.type === "dvd" ? `${item.duration} minutes` : `${item.page_count} pages`;
    return `the ${typeName(item)} '${item.title}' by ${item.author}, ${extra}`;
}

// ["'A'", "'B'", "'C'"] -> "'A', 'B' and 'C'"
function joinWords(words) {
    if (words.length <= 1) return words.join("");
    return `${words.slice(0, -1).join(", ")} and ${words[words.length - 1]}`;
}

// "I found 2 available books: 'Dune' and '1984'."
function listReply(path, items) {
    const query = new URLSearchParams(path.split("?")[1] || "");
    const state = { true: "available ", false: "checked-out " }[query.get("available")] || "";
    const [one, many] = { book: ["book", "books"], dvd: ["DVD", "DVDs"] }[query.get("type")]
        || ["item", "items"];

    if (items.length === 0) return `There are no ${state}${many} right now.`;

    const titles = items.slice(0, MAX_SPOKEN_TITLES).map((item) => `'${item.title}'`);
    if (items.length > MAX_SPOKEN_TITLES) titles.push(`${items.length - MAX_SPOKEN_TITLES} more`);
    const noun = items.length === 1 ? one : many;
    return `I found ${items.length} ${state}${noun}: ${joinWords(titles)}.`;
}

function librarianReply(command, status, data) {
    const action = actionOf(command);
    const id = itemIdOf(command);

    // --- Errors ---
    if (status === 404 && id !== null) return `Sorry, item ${id} does not exist.`;
    if (status === 409 && action === "checkout") return `Sorry, item ${id} is already checked out.`;
    if (status === 409 && action === "return") return `Sorry, item ${id} is not checked out.`;
    if (status === 409 && action === "delete") {
        return `Sorry, item ${id} is checked out, so I can't delete it. Please return it first.`;
    }
    if (status >= 400) {
        // 400: read the API's own error message out loud ("page_count" -> "page count").
        const message = data && data.error ? data.error.replaceAll("_", " ") : `The server answered ${status}.`;
        return `Sorry, I couldn't do that. ${message}`;
    }

    // --- Success ---
    switch (action) {
        case "create":
            return `Successfully created ${typeName(data)} '${data.title}' with ID ${data.id}.`;
        case "list":
            return listReply(command.path, data);
        case "get": {
            const state = data.is_available ? "available" : "currently checked out";
            return `Item ${id} is ${describeItem(data)}. It is ${state}.`;
        }
        case "replace":
            return `Item ${id} has been replaced. It is now ${describeItem(data)}.`;
        case "update":
            return `Item ${id} has been updated. It is now ${describeItem(data)}.`;
        case "delete":
            return `Item ${id} has been removed from the library.`;
        case "checkout": {
            // The checkout answer is { item, message }; DVDs get a care reminder.
            const care = data.item.type === "dvd" ? " Please handle the disc with care." : "";
            return `Item ${id}, '${data.item.title}', has been checked out.${care}`;
        }
        case "return":
            return `Item ${id}, '${data.title}', has been returned. Thank you!`;
    }
}


// ---------- Voice log ----------

// "PATCH /api/items/3 {"page_count":250}"
function formatRequest(command) {
    const body = command.body === null ? "" : ` ${JSON.stringify(command.body)}`;
    return `${command.method} ${command.path}${body}`;
}

function logLine(label, text) {
    const line = document.createElement("p");
    const labelSpan = document.createElement("span");
    labelSpan.className = "label";
    labelSpan.textContent = label;
    const value = document.createElement("code");
    value.textContent = text;  // textContent, so titles can never inject HTML
    line.append(labelSpan, value);
    return line;
}

// Newest entry on top: heard -> request -> status -> librarian.
function addLogEntry({ source, heard, command, status, reply }) {
    const entry = document.createElement("li");
    if (status === null || status >= 400) entry.classList.add("failed");

    entry.append(
        logLine(source === "voice" ? "🎤 Heard" : "⌨️ Typed", `"${heard}"`),
        logLine("Request", command ? formatRequest(command) : "— not understood, no request sent"),
        logLine("Status", status === null ? "—" : `${status} ${STATUS_TEXT[status] || ""}`),
        logLine("Librarian", reply),
    );
    voiceLog.prepend(entry);
    // Drop the oldest entries (at the bottom) so the log never grows past the limit.
    while (voiceLog.children.length > MAX_LOG_ENTRIES) {
        voiceLog.lastElementChild.remove();
    }
}

clearLogButton.addEventListener("click", () => {
    voiceLog.innerHTML = "";
});


// ---------- Voice output (Azure text-to-speech) ----------

let speechQueue = Promise.resolve();  // replies are played one after another, in order
let speechGeneration = 0;             // bumped when recording starts, to drop queued replies
let currentAudio = null;

// Ask the server to synthesize the text. Returns an object URL for the WAV audio.
async function fetchSpeech(text) {
    const response = await fetch("/api/speak", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
    });
    if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.error || `Speech failed (${response.status})`);
    }
    return URL.createObjectURL(await response.blob());
}

function playAudio(url) {
    return new Promise((resolve) => {
        currentAudio = new Audio(url);
        currentAudio.onended = currentAudio.onpause = currentAudio.onerror = resolve;
        currentAudio.play().catch(resolve);
    });
}

function speak(text) {
    if (isRecording()) return;  // never talk over the microphone

    const generation = speechGeneration;
    const audioUrl = fetchSpeech(text);  // start fetching right away

    speechQueue = speechQueue.then(async () => {
        try {
            const url = await audioUrl;
            if (generation === speechGeneration) await playAudio(url);
            URL.revokeObjectURL(url);
        } catch (err) {
            setStatus(err.message);
        }
    });
}

function stopSpeaking() {
    speechGeneration++;
    if (currentAudio) currentAudio.pause();
}


// ---------- Voice input (MediaRecorder -> Azure speech-to-text) ----------

let mediaRecorder = null;

function isRecording() {
    return mediaRecorder !== null && mediaRecorder.state === "recording";
}

function setStatus(message) {
    voiceStatus.textContent = message;
}

async function sendRecording(blob) {
    micButton.disabled = true;
    setStatus("Recognizing…");

    // Chrome/Firefox record WebM; Safari records MP4 (same container as .m4a).
    const filename = blob.type.includes("mp4") ? "recording.m4a" : "recording.webm";
    const form = new FormData();
    form.append("audio", blob, filename);

    try {
        const response = await fetch("/api/voice/recognize", { method: "POST", body: form });
        const data = await response.json();
        if (!response.ok) {
            setStatus(data.error);
            speak(data.error);
            return;
        }
        await handleSentence(data.text, "voice");
    } catch (err) {
        setStatus("Could not reach the server.");
        speak("Could not reach the server.");
    } finally {
        micButton.disabled = false;
    }
}

async function startRecording() {
    let stream;
    try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
        setStatus("Microphone access was denied or is unavailable.");
        return;
    }

    stopSpeaking();  // the librarian goes quiet while you talk
    const chunks = [];
    mediaRecorder = new MediaRecorder(stream);
    mediaRecorder.ondataavailable = (e) => chunks.push(e.data);
    mediaRecorder.onstop = () => {
        stream.getTracks().forEach((track) => track.stop()); // turn off the mic indicator
        micButton.classList.remove("recording");
        micButton.setAttribute("aria-label", "Start recording");
        sendRecording(new Blob(chunks, { type: mediaRecorder.mimeType }));
    };

    mediaRecorder.start();
    micButton.classList.add("recording");
    micButton.setAttribute("aria-label", "Stop recording");
    setStatus("Listening… click the microphone again to stop.");
}

micButton.addEventListener("click", () => {
    if (isRecording()) mediaRecorder.stop();
    else startRecording();
});

// Typed commands take exactly the same path as spoken ones.
textCommandForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const text = textCommandInput.value;
    textCommandInput.value = "";
    await handleSentence(text, "typed");
});

"""Turn one spoken (or typed) sentence into one call to the library API.

parse(text) returns either a command:
    {"method": "PATCH", "path": "/api/items/3", "body": {"page_count": 250}}
or an error the librarian can say out loud:
    {"error": "Sorry, I didn't understand ..."}

The parser only builds the request. It does not check library rules
(missing fields, wrong types, unknown ids): the API does that and answers
with 400/404/409, and the frontend reads that answer out loud.
"""

import re
from urllib.parse import urlencode

EXAMPLE = "Try saying 'list available books' or 'check out item 3'."

# One example per command, used when the item number is missing.
EXAMPLES = {
    "show": "show item 3",
    "replace": "replace item 3, title 1984, author George Orwell, pages 328",
    "update": "update item 3, pages 250",
    "delete": "delete item 3",
    "checkout": "check out item 3",
    "return": "return item 3",
}


# --- Numbers: "3", "1,200", "three", "twenty-five", "item to" (= 2) ---

UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
# Azure sometimes writes a short number as a word that sounds the same.
# Only used for item numbers, and only when the number is a single word.
HOMOPHONES = {"won": 1, "to": 2, "too": 2, "for": 4, "fore": 4, "ate": 8}


def words_to_number(words):
    """["two", "hundred", "twenty"] -> 220. Returns None if a word is not a number word."""
    if not words:
        return None
    total = 0    # finished thousands
    current = 0  # the part below one thousand
    for word in words:
        if word in UNITS:
            current += UNITS[word]
        elif word in TENS:
            current += TENS[word]
        elif word == "hundred":
            current = max(current, 1) * 100
        elif word == "thousand":
            total += max(current, 1) * 1000
            current = 0
        elif word == "and":  # "two hundred and twenty"
            continue
        else:
            return None
    return total + current


def to_number(text, allow_homophones=False):
    """Turn "220", "1,200", "two hundred twenty" or "twenty-five" into an int, else None."""
    text = text.lower().strip(" .,")
    if re.fullmatch(r"\d+|\d{1,3}(?:,\d{3})+", text):
        return int(text.replace(",", ""))
    words = re.split(r"[\s-]+", text)
    if allow_homophones and len(words) == 1 and words[0] in HOMOPHONES:
        return HOMOPHONES[words[0]]
    return words_to_number(words)


# A digit run or any number word, longest words first so "seventeen" wins over "seven".
_NUMBER_WORDS = sorted({*UNITS, *TENS, *HOMOPHONES, "hundred", "thousand"}, key=len, reverse=True)
NUMBER = rf"(?:\d+|{'|'.join(_NUMBER_WORDS)})"

# "item 3", "item number three", "item no. 3", "item #3", "number 3", "ID 3"
ITEM_ID_PATTERN = re.compile(
    rf"\b(?:item|id|number)\s+(?:number\s+|no\.?\s*|#\s*)?#?"
    rf"(?P<number>{NUMBER}(?:[\s-]+{NUMBER})*)\b",
    re.IGNORECASE,
)


def find_item_id(text):
    """Return the item number in the sentence, or None."""
    match = ITEM_ID_PATTERN.search(text)
    if match is None:
        return None
    words = re.split(r"[\s-]+", match.group("number"))
    # The pattern may grab too much ("item 3 for me" -> "3 for"),
    # so try the longest run of words first and drop words from the end.
    for end in range(len(words), 0, -1):
        number = to_number(" ".join(words[:end]), allow_homophones=(end == 1))
        if number is not None:
            return number
    return None


# --- Item types ---

BOOK_PATTERN = re.compile(r"\bbooks?\b", re.IGNORECASE)
DVD_PATTERN = re.compile(r"\b(?:dvd|d\.\s?v\.\s?d\.?|movie|film)(?:'?s)?(?![a-z])", re.IGNORECASE)


def find_item_type(text):
    """Return "book" or "dvd" if exactly one of them is mentioned, else None."""
    is_book = BOOK_PATTERN.search(text) is not None
    is_dvd = DVD_PATTERN.search(text) is not None
    if is_book and not is_dvd:
        return "book"
    if is_dvd and not is_book:
        return "dvd"
    return None


# --- Fields: "title The Catcher in the Rye, author J.D. Salinger, pages 220" ---

# Spoken keyword -> field name in the API.
FIELD_NAMES = {
    "type": "type",
    "title": "title",
    "author": "author",
    "director": "author",
    "page count": "page_count",
    "number of pages": "page_count",
    "pages": "page_count",
    "page": "page_count",
    "duration": "duration",
    "running time": "duration",
    "minutes": "duration",
}

# Longer keywords first, so "page count" is not read as "page".
# (?!['’\w]) stops "author's" or "titles" from counting as a keyword.
FIELD_PATTERN = re.compile(
    r"\b(?:" + "|".join(
        keyword.replace(" ", r"[\s-]")
        for keyword in sorted(FIELD_NAMES, key=len, reverse=True)
    ) + r")(?!['’\w])",
    re.IGNORECASE,
)


def split_sentence(text):
    """Split the sentence at the field keywords.

    "update item 3, pages 250" -> ("update item 3, ", [("pages", " 250")])
    The head is everything before the first keyword; it holds the command words.
    """
    matches = list(FIELD_PATTERN.finditer(text))
    head = text[:matches[0].start()] if matches else text
    pairs = []
    for i, match in enumerate(matches):
        # A value runs until the next keyword (or the end of the sentence).
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        keyword = re.sub(r"[\s-]+", " ", match.group().lower())
        pairs.append((keyword, text[match.end():end]))
    return head, pairs


def read_fields(pairs, is_update):
    """Turn [("pages", " 250, ")] into {"page_count": 250}."""
    fields = {}
    for keyword, raw_value in pairs:
        name = FIELD_NAMES[keyword]
        # Remove the punctuation Azure puts between fields, and any quotes.
        value = raw_value.strip(" \t,.;:!?\"'“”‘’")
        # "change item 3 title to X" -> X
        if is_update and value.lower().startswith("to "):
            value = value[3:].strip()
        # Skip empty values, e.g. "minutes" in "duration 136 minutes".
        if not value or name in fields:
            continue

        if name in ("page_count", "duration"):
            number = to_number(value)
            # If it is not a number, send it as it is and let the API answer 400.
            fields[name] = number if number is not None else value
        elif name == "type":
            fields[name] = find_item_type(value) or value
        else:
            fields[name] = value
    return fields


# --- Command words ---

# The command word that comes first in the sentence wins, so in
# "list checked out DVDs" the command is "list", not "check out".
INTENT_PATTERNS = {
    "checkout": r"check[\s-]?out|borrow",
    "return": r"return|check[\s-]?in|bring back|give back",
    "create": r"create|add|new",
    "replace": r"replace|overwrite",
    "update": r"update|change|edit|modify|set",
    "delete": r"delete|remove",
    "show": r"list|show|get|display|find|what|which|tell me",
}


def find_intent(head):
    """Return the name of the earliest command word in the head, or None."""
    found = []
    for name, pattern in INTENT_PATTERNS.items():
        match = re.search(rf"\b(?:{pattern})\b", head, re.IGNORECASE)
        if match:
            found.append((match.start(), name))
    return min(found)[1] if found else None


def list_query(head, fields):
    """Build the ?available= and ?type= filters for a list command."""
    query = {}
    if re.search(r"\b(?:checked[\s-]?out|borrowed|unavailable|not available|on loan)\b",
                 head, re.IGNORECASE):
        query["available"] = "false"
    elif re.search(r"\b(?:available|in stock|on the shelf)\b", head, re.IGNORECASE):
        query["available"] = "true"

    item_type = fields.get("type") or find_item_type(head)
    if item_type:
        query["type"] = item_type
    return query


# --- Main entry point ---

def command(method, path, body=None):
    return {"method": method, "path": path, "body": body}


def error(message):
    return {"error": message}


def parse(text):
    """Turn one sentence into {"method", "path", "body"} or {"error"}."""
    text = (text or "").strip()
    if not text:
        return error(f"I didn't hear anything. {EXAMPLE}")

    head, pairs = split_sentence(text)
    intent = find_intent(head)
    if intent is None:
        return error(f"Sorry, I didn't understand '{text}'. {EXAMPLE}")

    fields = read_fields(pairs, is_update=(intent == "update"))

    if intent == "create":
        # "Create a DVD, title ..." also works without the word "type".
        item_type = fields.get("type") or find_item_type(head)
        body = {"type": item_type, **fields} if item_type else fields
        return command("POST", "/api/items", body)

    item_id = find_item_id(text)

    if intent == "show" and item_id is None:
        query = list_query(head, fields)
        path = "/api/items?" + urlencode(query) if query else "/api/items"
        return command("GET", path)

    if item_id is None:
        return error(f"Which item? Please say the item number, for example '{EXAMPLES[intent]}'.")

    path = f"/api/items/{item_id}"
    if intent == "show":
        return command("GET", path)
    if intent == "replace":
        return command("PUT", path, fields)
    if intent == "update":
        return command("PATCH", path, fields)
    if intent == "delete":
        return command("DELETE", path)
    if intent == "checkout":
        return command("POST", f"{path}/checkout")
    return command("POST", f"{path}/return")  # intent == "return"

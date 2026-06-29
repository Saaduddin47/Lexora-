"""Natural-language calendar: parse dates/times from chat, detect conflicts,
and build a one-click 'Add to Google Calendar' link. Events live in the app store
(so they reflect in the client's memory + knowledge graph)."""
import re
from datetime import datetime, timedelta
from urllib.parse import quote

import dateparser
from dateparser.search import search_dates

_SCHED_CUES = ("schedule", "meeting", "appointment", "hearing", "remind", "reminder",
               "book a", "set a", " meet ", "court", " call ", "session", "deadline",
               "visit", "follow up", "follow-up", "consultation")
# words that mark the sentence as past testimony, NOT a scheduling request
_TESTIMONY = ("said", "told", "was ", "were ", "claims", "claimed", "statement",
              "insists", "denies", "denied", "alleges", "testified")

_FILLER = re.compile(
    r"^(i have|i've got|i have got|there is|there's|i need|i want|please|can you|"
    r"schedule|set up|set|book|add|put|remind me( to| about)?|a|an|the|my|to|for)\b",
    re.I)


def _make_title(text, date_phrase):
    t = text.replace(date_phrase, " ") if date_phrase else text
    t = re.sub(r"\b(at|on|by|from|to|next|this|tomorrow|today)\b", " ", t, flags=re.I)
    t = re.sub(r"\s+", " ", t).strip(" .,-")
    prev = None
    while t and t != prev:                       # peel leading filler words
        prev = t
        t = _FILLER.sub("", t).strip(" .,-")
    t = re.sub(r"\s+", " ", t).strip(" .,-")
    if not t or len(t) < 2:
        return "Meeting"
    return t[0].upper() + t[1:]


# clock times like "5pm", "11 am", "3:30 pm", "at 14:00"
_TIME_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s*m\.?\b", re.I)
_TIME24_RE = re.compile(r"\bat\s+(\d{1,2}):(\d{2})\b")


def parse_event(text, base=None):
    """Return {title, start, end} (datetimes) if the text schedules something, else None."""
    low = " " + text.lower() + " "
    if not any(c in low for c in _SCHED_CUES):
        return None
    if any(w in low for w in _TESTIMONY):
        return None
    base = base or datetime.now()

    # 1) pull the TIME out first with a regex (so "11am" isn't read as 'day 11')
    hour = minute = None
    time_span = None
    m = _TIME_RE.search(text)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2) or 0)
        ap = m.group(3).lower()
        if ap == "p" and hour < 12:
            hour += 12
        if ap == "a" and hour == 12:
            hour = 0
        time_span = (m.start(), m.end())
    else:
        m24 = _TIME24_RE.search(text)
        if m24:
            hour, minute = int(m24.group(1)), int(m24.group(2))
            time_span = (m24.start(), m24.end())

    text_wo_time = (text[:time_span[0]] + " " + text[time_span[1]:]) if time_span else text

    # 2) find the DATE from the remaining text
    date_dt = None
    date_phrases = []
    try:
        found = search_dates(text_wo_time, settings={"PREFER_DATES_FROM": "future",
                                                     "RELATIVE_BASE": base,
                                                     "DATE_ORDER": "DMY",
                                                     "RETURN_AS_TIMEZONE_AWARE": False})
    except Exception:  # noqa: BLE001
        found = None
    if found:
        date_phrases = [p for p, _ in found]
        date_dt = next((d for _, d in found if d.date() != base.date()), found[0][1])

    if hour is None and date_dt is None:
        return None                              # no time and no date -> not a scheduling line

    base_day = date_dt or base
    if hour is None:                             # date given but no clock time
        hour, minute = (base_day.hour, base_day.minute) if (base_day.hour or base_day.minute) else (9, 0)
    start = base_day.replace(hour=hour, minute=minute, second=0, microsecond=0)
    end = start + timedelta(hours=1)

    # 3) title = original text minus the time + date phrases, cleaned
    title = text
    if time_span:
        title = title.replace(text[time_span[0]:time_span[1]], " ")
    for p in date_phrases:
        title = title.replace(p, " ")
    return {"title": _make_title(title, ""), "start": start, "end": end}


def human(dt):
    return dt.strftime("%a %d %b %Y, %I:%M %p").replace(" 0", " ")


def _fmt(dt):
    return dt.strftime("%Y%m%dT%H%M%S")


def gcal_link(title, start, end, details=""):
    dates = f"{_fmt(start)}/{_fmt(end)}"
    url = ("https://calendar.google.com/calendar/render?action=TEMPLATE"
           f"&text={quote(title)}&dates={dates}")
    if details:
        url += f"&details={quote(details)}"
    return url


def to_iso(dt):
    return dt.replace(microsecond=0).isoformat()


def from_iso(s):
    try:
        return datetime.fromisoformat(s)
    except Exception:  # noqa: BLE001
        return None

"""Introductory AI utilities: lexicon sentiment, extractive summary and FAQ chatbot."""
import re
from collections import Counter

POSITIVE = {"clean", "good", "better", "improved", "fresh", "thank", "resolved", "excellent", "safe"}
NEGATIVE = {"pollution", "smog", "bad", "poor", "cough", "breathing", "sick", "dust", "smoke", "worse", "dangerous"}

def sentiment(text):
    tokens = re.findall(r"[a-z']+", text.lower())
    score = sum(t in POSITIVE for t in tokens) - sum(t in NEGATIVE for t in tokens)
    label = "positive" if score > 0 else "negative" if score < 0 else "neutral"
    return {"label": label, "score": score}

def extractive_summary(text, max_sentences=2):
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    if len(sentences) <= max_sentences:
        return text.strip()
    words = re.findall(r"[a-z']+", text.lower())
    stop = {"the","a","an","is","are","to","of","and","in","on","for","it","this","that"}
    freq = Counter(w for w in words if w not in stop)
    scored = []
    for i, sentence in enumerate(sentences):
        terms = re.findall(r"[a-z']+", sentence.lower())
        scored.append((sum(freq[t] for t in terms), i, sentence))
    chosen = sorted(sorted(scored, reverse=True)[:max_sentences], key=lambda x:x[1])
    return " ".join(x[2] for x in chosen)

def chatbot(message):
    q = message.lower()
    if any(x in q for x in ("pm2.5","pm25")):
        return "PM2.5 is fine particulate matter. Check the latest station and daily PM2.5 summary; elevated values need public-health review."
    if "pm10" in q:
        return "PM10 measures inhalable particles. Compare daily averages and station-level patterns in the dashboard."
    if any(x in q for x in ("complaint","report","submit")):
        return "Please report the station/location, date and time, visible pollution source, and a short description. Avoid sharing personal information."
    if any(x in q for x in ("trend","monthly","month")):
        return "Use the monthly_summary query to compare month-level pollutant averages and peaks."
    if any(x in q for x in ("hello","hi","help")):
        return "Hello. Ask about PM2.5, PM10, monthly trends, or how to submit an air-quality complaint."
    return "I can help with PM2.5, PM10, monthly trends, and complaint submission. Please rephrase your question."

if __name__ == "__main__":
    samples = ["The air is clean and fresh today.", "Heavy smoke and pollution caused cough."]
    for s in samples: print(sentiment(s), "=>", extractive_summary(s))
    print(chatbot("How can I submit a complaint?"))

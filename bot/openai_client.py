from bot.filters import Filters
from processor.normalize import YEREVAN_DISTRICTS

SYSTEM_PROMPT = (
    "You convert a user's apartment-rental search request into structured filters "
    "for a Yerevan rentals database. The user may write in Russian, English, or "
    "Armenian. Prices are AMD (֏) or USD ($). Only set a field the user clearly "
    "specifies; leave the rest null. If the user names a Yerevan place (district, "
    "neighborhood, synonym, Russian/Armenian form, or transliteration), set "
    "`district` to EXACTLY ONE of these canonical English names: "
    + ", ".join(YEREVAN_DISTRICTS)
    + ". If none clearly matches, leave `district` null. Choose a "
    "`sort` only if the user implies one (e.g. 'cheapest' -> price_asc)."
)


def parse_query(text: str, client, model: str) -> Filters:
    completion = client.beta.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        response_format=Filters,
    )
    return completion.choices[0].message.parsed


def transcribe(file_path: str, client, model: str) -> str:
    with open(file_path, "rb") as f:
        result = client.audio.transcriptions.create(model=model, file=f)
    return result.text

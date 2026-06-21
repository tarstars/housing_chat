def transcribe(file_path: str, client, model: str) -> str:
    with open(file_path, "rb") as f:
        result = client.audio.transcriptions.create(model=model, file=f)
    return result.text

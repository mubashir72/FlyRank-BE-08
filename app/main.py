from fastapi import FastAPI

app = FastAPI(title="Sales Report Pipeline")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

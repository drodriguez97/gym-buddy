from fastapi import FastAPI

app = FastAPI(title="gym-buddy")

@app.get("/health")
def health():
        return {"status" : "ok"}
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class PromptRequest(BaseModel):
    prompt: str

@app.post("/generate")
def generate(request: PromptRequest):
    # Return a valid SQL query for the mock DB
    return {"text": "SELECT date, amount FROM sales ORDER BY date;"}

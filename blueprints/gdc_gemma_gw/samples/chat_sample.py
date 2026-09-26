import os
import time
import base64
from openai import OpenAI

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def run_interactive_chat():
    base_url = os.getenv("GATEWAY_URL", "http://localhost:8080/v1")
    api_key = "gdc-no-auth-required"

    client = OpenAI(base_url=base_url, api_key=api_key)
    print(f"🔗 Connected to Gemma 4 Gateway at {base_url}")
    print("💡 Tip: Type an image file path to test vision (e.g., 'analyze image.png'). Type 'exit' to quit.\n")

    chat_history = [{"role": "system", "content": "You are a highly capable AI agent operating on Google Distributed Cloud. You MUST output your step-by-step thinking process wrapped in <thought>...</thought> tags before your final answer."}]

    while True:
        user_input = input("👤 You: ").strip()
        if user_input.lower() in ['exit', 'quit']:
            break
        if not user_input:
            continue

        # Thinking mode toggle commands
        if user_input.lower() == "/thinking off":
            chat_history[0]["content"] = "You are a highly capable AI agent operating on Google Distributed Cloud. Do not show your thinking process."
            print("🟢 Thinking mode disabled for subsequent queries.")
            continue
        if user_input.lower() == "/thinking on":
            chat_history[0]["content"] = "You are a highly capable AI agent operating on Google Distributed Cloud. You MUST output your step-by-step thinking process wrapped in <thought>...</thought> tags before your final answer."
            print("🧠 Thinking mode enabled for subsequent queries.")
            continue

        # Simple image detection hack for the CLI
        image_b64 = None
        prompt_text = user_input
        if " " in user_input and user_input.split()[-1].endswith(('.png', '.jpg', '.jpeg')):
            parts = user_input.rsplit(" ", 1)
            prompt_text = parts[0]
            image_path = parts[1]
            if os.path.exists(image_path):
                print(f"📸 Loading image: {image_path}")
                image_b64 = encode_image(image_path)
            else:
                print("❌ Image file not found.")

        # Build Message
        if image_b64:
            message_content = [
                {"type": "text", "text": prompt_text},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
            ]
        else:
            message_content = prompt_text

        chat_history.append({"role": "user", "content": message_content})

        start_time = time.time()
        try:
            response = client.chat.completions.create(
                model="gemma4",
                messages=chat_history,
                temperature=0.7,
                stream=True
            )
            
            bot_response = ""
            variant_printed = False
            for chunk in response:
                if not variant_printed and chunk.model:
                    print(f"\n🧠 Gemma 4 (Variant: {chunk.model}) [live]:")
                    variant_printed = True

                if chunk.choices[0].delta.content:
                    content_chunk = chunk.choices[0].delta.content
                    print(content_chunk, end="", flush=True)
                    bot_response += content_chunk
            print("\n")
            
            # Store text response in history
            chat_history.append({"role": "assistant", "content": bot_response})

        except Exception as e:
            print(f"❌ Error: {e}")
            chat_history.pop() # Remove failed user prompt

if __name__ == "__main__":
    run_interactive_chat()

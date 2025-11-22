import os 
import sys
import time 
from huggingface_hub import InferenceClient

HF_TOKEN = os.environ.get("HF_TOKEN")
MODEL_ID = "meta-llama/Meta-Llama-3-8B-Instruct"
API_BASE_URL = "https://router.huggingface.co/v1/"

# 1. Define the Conversation History Structure 
# Start with a system message to set the AI's persona and tone.
conversation_history = [
    {
        "role": "system",
        "content": "You are friendly, detail oriented and concise AI assistant named 'HUGG'. Keep your answers accurate and brief."
    }
]

# 2. Setup the Inference Client
def initialize_client():
    if not HF_TOKEN:
        print("ERROR: HF_TOKEN environment variable is not set.")
        print("Please obtain your token from Hugging Face and set the variable.")
        sys.exit(1)

    try:
        client = InferenceClient(
            base_url=API_BASE_URL,
            api_key=HF_TOKEN
        )
        return client
    except Exception as e:
        print(f"Error initializing InferenceClient: {e}")
        sys.exit(1)


def chat_with_hf_api_and_history(client: InferenceClient, prompt: str):
    """
    Sends the full conversation history + new prompt to the API and updates history.
    Implements basic exponential backoff for retries.
    """

    global conversation_history

    # Append the new user message
    conversation_history.append({"role":"user", "content":prompt})
 
    # Pass the ENTIRE history list to the 'messages' parameter
    completion = client.chat.completions.create(
        model=MODEL_ID,
        messages=conversation_history,
        max_tokens=50,
        temperature=0.7,
        stream=False
    )

    # Extract the AI's response content
    ai_response_content = completion.choices[0].message.content

    # Append the AI's response to the history for the next turn
    conversation_history.append({"role":"assistant", "content":ai_response_content})

    return ai_response_content

# 3. Main Interactive Loop
def main():
    """Runs the main command-line chat application."""
    client = initialize_client()

    print("\n--- Hugging Face Interactive Chat Assistant ---")
    print(f"Model: {MODEL_ID}")
    print("Type 'quit' or 'exit' to end the session.")

    # Display the system's opening message/persona
    print(f"\n🤖 Hugg: {conversation_history[0]['content']}")

    while True:
        try:
            user_input = input("\n You: ")

            if user_input.lower() in ['quit', 'exit']:
                print("\n🤖 Hugg: Goodbye! It was great chatting with you.")
                break
                
            if not user_input.strip():
                continue
            
            # Get the AI response
            ai_response = chat_with_hf_api_and_history(client, user_input)

            print(f"\n HUGG: {ai_response}")

        except KeyboardInterrupt:
            print("\n\n🤖 Hugg: Goodbye! It was great chatting with you.")
            break
        except Exception as e:
            print(f"\nAn unexpected error occurred: {e}")
            break

if __name__ == "__main__":
    main()
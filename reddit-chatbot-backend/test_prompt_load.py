import os

def test_load_llm_prompt(file_path="llm_prompt.txt"):
    print(f"Attempting to load prompt from: {os.path.abspath(file_path)}")
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            print("\n--- Successfully Loaded Prompt Content (first 200 chars) ---")
            print(content[:200], "...")
            print("\n--- End of Prompt Content ---")
            return content
    except FileNotFoundError:
        print(f"ERROR: Prompt file '{file_path}' NOT FOUND. Please ensure it's in the same directory.")
        return None
    except Exception as e:
        print(f"ERROR: An unexpected error occurred while reading the prompt file: {e}")
        return None

if __name__ == "__main__":
    loaded_prompt = test_load_llm_prompt()
    if loaded_prompt:
        print("Prompt loaded successfully in test script.")
    else:
        print("Prompt failed to load in test script.")
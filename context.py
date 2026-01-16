def read_relevant_file(file_path, max_lines=50):
    """Read the first `max_lines` of a file."""
    try:
        with open(file_path, 'r') as file:
            lines = file.readlines()
            content = ''.join(lines[:max_lines])
            print(f"File content preview:\n{content}")  # Debug print
            return content
    except FileNotFoundError:
        print(f"Error: File {file_path} not found.")  # Debug print
        return f"Error: File {file_path} not found."
    except Exception as e:
        print(f"Error reading file: {e}")  # Debug print
        return f"Error reading file: {e}"

    
def search_in_file(file_path, keyword):
    """Search for a keyword in the file using Python (Windows-compatible)."""
    try:
        # Use the function name from the bug description
        function_name = keyword.split()[0]  # Extract the first word
        matches = []
        with open(file_path, "r") as f:
            for i, line in enumerate(f, 1):
                if function_name in line:
                    matches.append(f"{i}:{line.strip()}")
        
        return "\n".join(matches) if matches else "No matches found."
    except Exception as e:
        return f"Error searching file: {e}"


def build_prompt(file_path, bug_description):
    """Build the prompt for Mistral API."""
    file_content = read_relevant_file(file_path)
    # Extract function name from bug description
    function_name = bug_description.split()[0]  # e.g., "TypeError" -> focus on "calculate_total"
    error_context = search_in_file(file_path, function_name)  # Dynamic search

    prompt = f"""
    File: {file_path}
    Content:
    {file_content}

    Error Context:
    {error_context}

    Task: The following error was reported: {bug_description}
    Suggest a fix for the code in {file_path}.
    Respond with the corrected code inside a Python code block (```python ... ```).
    """
    return prompt


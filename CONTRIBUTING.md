# Contributing to Mistral CLI

Thank you for your interest in contributing to Mistral CLI! We welcome contributions from everyone.

## Getting Started

1.  **Fork the repository** on GitHub.
2.  **Clone your fork** locally:
    ```bash
    git clone https://github.com/your-username/mistral-cli.git
    cd mistral-cli
    ```
3.  **Create a virtual environment**:
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```
4.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

## Development Workflow

1.  Create a new branch for your feature or bugfix:
    ```bash
    git checkout -b feature/my-new-feature
    ```
2.  Make your changes.
3.  **Test your changes**:
    *   Create a dummy python file with a bug (like `test_bug.py`).
    *   Run the CLI against it: `python main.py fix test_bug.py "description" --dry-run`
    *   Ensure no regressions in existing features.

## Coding Standards

*   Follow PEP 8 guidelines.
*   Keep functions small and focused.
*   Add comments for complex logic.
*   **Safety First**: Ensure any new file-writing logic has backups and user confirmation.

## Submitting a Pull Request

1.  Push your branch to your fork:
    ```bash
    git push origin feature/my-new-feature
    ```
2.  Open a Pull Request on the main repository.
3.  Describe your changes clearly.

## Reporting Bugs

Please open an issue on GitHub with:
1.  The bug description.
2.  Steps to reproduce.
3.  Are you on Windows, Linux, or Mac?
4.  (Optional) Relevant logs from `mistral-cli.log`.

Thank you for helping make Mistral CLI better!

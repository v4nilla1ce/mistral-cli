# Mistral CLI - 7 Day MVP Plan

## Overview
This document outlines the step-by-step plan to build a Mistral CLI tool that fixes Python bugs using the Mistral API, following the principles of an open-source, API-based approach.

---

## Day 1: Project Setup and Core Structure

### Goals:
- Set up project infrastructure
- Create basic CLI interface
- Establish API connection foundation

### Tasks:
1. **Project Initialization**
   - Create GitHub repository `mistral-cli`
   - Set up Python project structure
   - Create `.gitignore` and `README.md`

2. **Environment Setup**
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install requests click rich python-dotenv transformers
   ```

3. **CLI Skeleton**
   - Create `main.py` with Click framework
   - Implement basic `fix` command
   - Add argument parsing for file and bug description

4. **API Wrapper**
   - Create `mistral_api.py`
   - Implement `MistralAPI` class with authentication
   - Test API connection with sample request

   ```python
   # main.py (Day 1 version)
   import click

   @click.group()
   def cli():
       """Mistral CLI: Fix Python bugs using Mistral API"""
       pass

   @click.command()
   @click.argument("file")
   @click.argument("bug_description")
   def fix(file, bug_description):
       """Basic fix command implementation"""
       click.echo(f"Preparing to fix {file}: {bug_description}")
   ```

---

## Day 2: Context Gathering System

### Goals:
- Implement local context gathering
- Create intelligent prompt construction
- Test context collection

### Tasks:
1. **File Reading**
   - Implement `read_relevant_file()` in `context.py`
   - Read first 50 lines of files
   - Add error handling

2. **Error Context Search**
   - Implement `search_in_file()` using grep
   - Extract relevant error information
   - Handle search failures

3. **Prompt Construction**
   - Create `build_prompt()` function
   - Combine file content with error context
   - Format for Mistral API

   ```python
   # context.py (Day 2 version)
   def build_prompt(file_path, bug_description):
       """Construct context-rich prompt for Mistral"""
       file_content = read_relevant_file(file_path)
       error_info = search_in_file(file_path, bug_description.split()[0])
       return f"""
       File: {file_path}
       Content:
       {file_content}

       Error: {bug_description}
       Context:
       {error_info}
       """
   ```

---

## Day 3: API Integration and Testing

### Goals:
- Connect context gathering to API
- Implement response handling
- Test end-to-end flow

### Tasks:
1. **API Integration**
   - Connect prompt construction to API call
   - Handle API responses and errors
   - Implement token management

2. **Testing Framework**
   - Create test Python files with bugs
   - Verify context collection
   - Test API communication

3. **Error Handling**
   - Add robust error messages
   - Handle API failures gracefully
   - Log issues for debugging

---

## Day 4: User Experience Enhancements

### Goals:
- Add user confirmation system
- Implement logging
- Create safety features

### Tasks:
1. **User Confirmation**
   - [x] Add interactive confirmation before fixes
   - [x] Implement `--dry-run` flag
   - [x] Add cancel option

2. **Session Logging**
   - [x] Create `mistral-cli.log`
   - [x] Log all actions and decisions
   - [x] Add timestamp to entries

3. **Safety Features**
   - [x] Implement file backup option (`.bak` files)
   - [x] Add change verification (Regex code extraction)
   - [ ] Create restore points

   ```python
   # Enhanced fix command
   def fix(file, bug_description):
       prompt = build_prompt(file, bug_description)
       suggestion = api.chat(prompt)

       if click.confirm("Apply this fix?"):
           apply_fix(file, suggestion)
       else:
           click.echo("Fix cancelled")
   ```

---

## Day 5: Token Management and Optimization

### Goals:
- Implement token counting
- Add context optimization
- Improve performance

### Tasks:
1. **Token Counting**
   - Add tokenizer integration
   - Implement token counting
   - Display token usage

2. **Context Optimization**
   - Implement context truncation
   - Add relevance filtering
   - Optimize for 10k token limit

3. **Performance Testing**
   - Test with various file sizes
   - Measure API response times
   - Optimize prompt construction

---

## Day 6: Documentation and Polish

### Goals:
- Create comprehensive documentation
- Add contribution guidelines
- Polish user interface

### Tasks:
1. **Documentation**
   - Complete `README.md`
   - Add installation instructions
   - Include usage examples

2. **Contribution Guidelines**
   - Create `CONTRIBUTING.md`
   - Define coding standards
   - Add testing instructions

3. **User Interface**
   - Improve command output formatting
   - Add color coding
   - Implement progress indicators

### Example README.md Section
#### Usage

1. Set your API key:
   ```bash
   export MISTRAL_API_KEY=your_key
   ```

2. Fix a bug:
   ```bash
   python main.py fix app.py "TypeError in calculate_total"
   ```

3. Dry run mode:
   ```bash
   python main.py fix app.py "bug" --dry-run
   ```

---

## Day 7: Open-Source Launch

### Goals:
- Final testing
- Prepare for public release
- Create community resources

### Tasks:
1. **Final Testing**
   - Complete end-to-end testing
   - Verify all features
   - Fix any remaining issues

2. **Open-Source Preparation**
   - Review all code
   - Ensure proper licensing
   - Prepare repository

3. **Community Resources**
   - Create issue templates
   - Set up contribution guidelines
   - Prepare announcement materials

---

## Key Principles

1. **API-Based Approach**: Leveraging Mistral's large models
2. **Open-Source**: Building a community-driven project
3. **Safety First**: User confirmation for all actions
4. **Contextual Awareness**: Intelligent context gathering
5. **Extensibility**: Designed for future plugins and features

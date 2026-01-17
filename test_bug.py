# test_bug.py
import logging

def calculate_total(items):
    """
    Calculate the total of a list of items.

    Args:
        items: List of numbers or strings to be summed or concatenated

    Returns:
        The sum of numbers or concatenated string

    Raises:
        ValueError: If the input list is empty or contains mixed types
    """
    if not items:
        raise ValueError("Input list cannot be empty")

    # Check if all items are numbers or all are strings
    all_numbers = all(isinstance(item, (int, float)) for item in items)
    all_strings = all(isinstance(item, str) for item in items)

    if not (all_numbers or all_strings):
        raise ValueError("All items must be of the same type (numbers or strings)")

    total = 0 if all_numbers else ""
    for item in items:
        total += item
    return total

def main():
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    try:
        # Test with numbers
        numbers = [1, 2, 3]
        logger.info(f"Calculating total for numbers: {numbers}")
        print(calculate_total(numbers))

        # Test with strings
        strings = ["Hello, ", "world!", " How are you?"]
        logger.info(f"Calculating total for strings: {strings}")
        print(calculate_total(strings))

        # Test with empty list (should raise error)
        # empty_list = []
        # print(calculate_total(empty_list))

        # Test with mixed types (should raise error)
        # mixed_list = [1, "two", 3.0]
        # print(calculate_total(mixed_list))

    except ValueError as e:
        logger.error(f"Error: {e}")

if __name__ == "__main__":
    main()
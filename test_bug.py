# test_bug.py
def calculate_total(items):
    total = 0
    for item in items:
        total += item
    return total

def main():
    numbers = [1, 2, 3]
    print(calculate_total(numbers))

if __name__ == "__main__":
    main()
import re


def extract_first_last_match(pattern):
    # 找到pattern的第一个匹配部分
    start_match = re.match(r"^\^?(\[[^\]]+\]|[A-Za-z0-9]+|\([^)]+\))", pattern)
    first_part = start_match.group(1) if start_match else None

    # 找到pattern的最后一个匹配部分
    end_match = re.search(r"(\([^)]+\)|\[[^\]]+\]|[A-Za-z0-9]+)\$?$", pattern)
    last_part = end_match.group(1) if end_match else None

    return first_part, last_part


def trim_to_nearest_match(string, pattern):
    """
    Tries to match the pattern directly to the string. If it matches, return the match.
    If not, iteratively expand from the first and last matched parts of the pattern within the string.
    """
    # Attempt a full match first
    full_match = re.match(pattern, string)
    if full_match:
        return full_match.group()  # Return if full match is found

    # Extract first and last identifiable groups from the pattern
    first_part, last_part = extract_first_last_match(pattern)

    # Build a new regex to capture nearest range in the string
    if first_part and last_part:
        regex = re.compile(rf"{first_part}.*?{last_part}", re.IGNORECASE)
        partial_match = regex.search(string)
        if partial_match:
            return partial_match.group()  # Return closest match within the bounds of first and last

    return string  # Return original string if no match found


# 示例测试
strings = [
    "randomtext02:30 PMextratext",
    "extrachars11:45 AMmorechars",
    "othertext08:15 PMendtext",
    "novalidhere",
    "1234othertext08:15PMmorechars5678"
]
pattern = r"^(0[1-9]|1[0-2]):[0-5][0-9]\s?(AM|PM)$"
results_1_improved = [(s, trim_to_nearest_match(s, pattern)) for s in strings]

# 其他pattern示例
pattern_2 = r"^[A-Z]{2}[0-9]{4}[A-Z]$"  # 匹配两位大写字母+4位数字+一位大写字母的字符串
strings_2 = [
    "123AB1234CDE",
    "XY5678Zmore",
    "invalid_string",
    "beginXY1234Zend",
    "AB1234C"
]
results_2_improved = [(s, trim_to_nearest_match(s, pattern_2)) for s in strings_2]

# 输出结果
print("Pattern 1 Results:")
for original, trimmed in results_1_improved:
    print(f"原始: {original} -> 修剪后: {trimmed}")

print("\nPattern 2 Results:")
for original, trimmed in results_2_improved:
    print(f"原始: {original} -> 修剪后: {trimmed}")
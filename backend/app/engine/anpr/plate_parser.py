import re
from typing import Optional, Tuple

DIGIT_TO_LETTER = {
    '0': 'O',
    '1': 'I',
    '2': 'Z',
    '4': 'A',
    '5': 'S',
    '8': 'B'
}

LETTER_TO_DIGIT = {
    'O': '0',
    'D': '0',
    'I': '1',
    'L': '1',
    'Z': '2',
    'A': '4',
    'S': '5',
    'G': '6',
    'B': '8',
    'T': '7'
}

# Indonesian valid region codes (Prefix)
VALID_REGIONS = {
    "A", "B", "D", "E", "F", "G", "H", "K", "L", "M", "N", "P", "R", "S", "T", "W", "Z",
    "AA", "AB", "AD", "AE", "AG", "BA", "BB", "BD", "BE", "BG", "BH", "BK", "BL", "BM",
    "BN", "BP", "DA", "DB", "DC", "DD", "DE", "DG", "DH", "DK", "DL", "DM", "DN", "DP",
    "DR", "DT", "DW", "EA", "EB", "ED", "KB", "KH", "KT", "KU", "PA", "PB"
}

def clean_ocr_text(text: str) -> str:
    """Remove special characters and standardize spaces."""
    cleaned = re.sub(r'[^A-Za-z0-9]', ' ', text.upper())
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned

def normalize_indonesian_plate(raw_text: str) -> Tuple[str, bool]:
    """
    Parse and rectify OCR plate string to standard Indonesian plate format:
    [REGION: 1-2 letters] [NUMBER: 1-4 digits] [SUFFIX: 1-3 letters]
    Returns (formatted_plate, is_valid_format).
    """
    cleaned = clean_ocr_text(raw_text)
    tokens = cleaned.split()

    if len(tokens) == 3:
        prefix_part, num_part, suffix_part = tokens[0], tokens[1], tokens[2]
    elif len(tokens) == 2:
        # Check if first part has prefix+number or number+suffix
        m = re.match(r'^([A-Z0-9]{1,2})([0-9]{1,4})$', tokens[0])
        if m:
            prefix_part, num_part, suffix_part = m.group(1), m.group(2), tokens[1]
        else:
            m2 = re.match(r'^([0-9]{1,4})([A-Z0-9]{1,3})$', tokens[1])
            if m2:
                prefix_part, num_part, suffix_part = tokens[0], m2.group(1), m2.group(2)
            else:
                return cleaned, False
    elif len(tokens) == 1 and len(tokens[0]) >= 4:
        # Single string without spaces, e.g. "B1234CD"
        m = re.match(r'^([A-Za-z0-9]{1,2})([0-9A-Za-z]{1,4})([A-Za-z0-9]{1,3})$', tokens[0])
        if m:
            prefix_part, num_part, suffix_part = m.group(1), m.group(2), m.group(3)
        else:
            return cleaned, False
    else:
        return cleaned, False

    # Rectify prefix: must be letters
    rectified_prefix = "".join(DIGIT_TO_LETTER.get(c, c) for c in prefix_part)
    # Rectify number: must be digits
    rectified_num = "".join(LETTER_TO_DIGIT.get(c, c) for c in num_part)
    # Rectify suffix: must be letters
    rectified_suffix = "".join(DIGIT_TO_LETTER.get(c, c) for c in suffix_part)

    # Validate syntax
    is_valid = (
        rectified_prefix in VALID_REGIONS and
        rectified_num.isdigit() and 1 <= len(rectified_num) <= 4 and
        rectified_suffix.isalpha() and 1 <= len(rectified_suffix) <= 3
    )

    formatted = f"{rectified_prefix} {rectified_num} {rectified_suffix}"
    return formatted, is_valid

def levenshtein_distance(s1: str, s2: str) -> int:
    """Calculate edit distance between two strings."""
    s1, s2 = s1.replace(" ", "").upper(), s2.replace(" ", "").upper()
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]

def match_plate_fuzzy(query_plate: str, target_plate: str, max_distance: int = 1) -> bool:
    """Return True if plates match closely (fuzzy search)."""
    p1 = query_plate.replace(" ", "").upper()
    p2 = target_plate.replace(" ", "").upper()
    if p1 in p2 or p2 in p1:
        return True
    return levenshtein_distance(p1, p2) <= max_distance

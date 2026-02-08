"""
Hindi Text Processor for Divya Vaani AI TTS
Handles Devanagari normalization, number conversion, and sentence segmentation.
"""
import re
import unicodedata
from typing import List, Tuple


# Hindi number words
HINDI_ONES = ['', 'एक', 'दो', 'तीन', 'चार', 'पाँच', 'छह', 'सात', 'आठ', 'नौ']
HINDI_TENS = ['', 'दस', 'बीस', 'तीस', 'चालीस', 'पचास', 'साठ', 'सत्तर', 'अस्सी', 'नब्बे']
HINDI_SPECIAL = {
    11: 'ग्यारह', 12: 'बारह', 13: 'तेरह', 14: 'चौदह', 15: 'पंद्रह',
    16: 'सोलह', 17: 'सत्रह', 18: 'अठारह', 19: 'उन्नीस',
    21: 'इक्कीस', 22: 'बाईस', 23: 'तेईस', 24: 'चौबीस', 25: 'पच्चीस',
    26: 'छब्बीस', 27: 'सत्ताईस', 28: 'अट्ठाईस', 29: 'उनतीस',
    31: 'इकतीस', 32: 'बत्तीस', 33: 'तैंतीस', 34: 'चौंतीस', 35: 'पैंतीस',
    36: 'छत्तीस', 37: 'सैंतीस', 38: 'अड़तीस', 39: 'उनतालीस',
    41: 'इकतालीस', 42: 'बयालीस', 43: 'तैंतालीस', 44: 'चवालीस', 45: 'पैंतालीस',
    46: 'छियालीस', 47: 'सैंतालीस', 48: 'अड़तालीस', 49: 'उनचास',
    51: 'इक्यावन', 52: 'बावन', 53: 'तिरेपन', 54: 'चौवन', 55: 'पचपन',
    56: 'छप्पन', 57: 'सत्तावन', 58: 'अट्ठावन', 59: 'उनसठ',
    61: 'इकसठ', 62: 'बासठ', 63: 'तिरेसठ', 64: 'चौंसठ', 65: 'पैंसठ',
    66: 'छियासठ', 67: 'सड़सठ', 68: 'अड़सठ', 69: 'उनहत्तर',
    71: 'इकहत्तर', 72: 'बहत्तर', 73: 'तिहत्तर', 74: 'चौहत्तर', 75: 'पचहत्तर',
    76: 'छिहत्तर', 77: 'सतहत्तर', 78: 'अठहत्तर', 79: 'उनासी',
    81: 'इक्यासी', 82: 'बयासी', 83: 'तिरासी', 84: 'चौरासी', 85: 'पचासी',
    86: 'छियासी', 87: 'सतासी', 88: 'अट्ठासी', 89: 'नवासी',
    91: 'इक्यानवे', 92: 'बानवे', 93: 'तिरानवे', 94: 'चौरानवे', 95: 'पंचानवे',
    96: 'छियानवे', 97: 'सत्तानवे', 98: 'अट्ठानवे', 99: 'निन्यानवे',
    100: 'सौ', 1000: 'हज़ार', 100000: 'लाख', 10000000: 'करोड़'
}


def number_to_hindi_words(num: int) -> str:
    """Convert a number to Hindi words."""
    if num == 0:
        return 'शून्य'
    
    if num < 0:
        return 'ऋण ' + number_to_hindi_words(-num)
    
    if num < 10:
        return HINDI_ONES[num]
    
    if num in HINDI_SPECIAL:
        return HINDI_SPECIAL[num]
    
    if num < 100:
        tens = num // 10
        ones = num % 10
        if ones == 0:
            return HINDI_TENS[tens]
        return HINDI_TENS[tens] + ' ' + HINDI_ONES[ones]
    
    if num < 1000:
        hundreds = num // 100
        remainder = num % 100
        result = HINDI_ONES[hundreds] + ' सौ'
        if remainder > 0:
            result += ' ' + number_to_hindi_words(remainder)
        return result
    
    if num < 100000:  # Less than 1 lakh
        thousands = num // 1000
        remainder = num % 1000
        result = number_to_hindi_words(thousands) + ' हज़ार'
        if remainder > 0:
            result += ' ' + number_to_hindi_words(remainder)
        return result
    
    if num < 10000000:  # Less than 1 crore
        lakhs = num // 100000
        remainder = num % 100000
        result = number_to_hindi_words(lakhs) + ' लाख'
        if remainder > 0:
            result += ' ' + number_to_hindi_words(remainder)
        return result
    
    # Crores
    crores = num // 10000000
    remainder = num % 10000000
    result = number_to_hindi_words(crores) + ' करोड़'
    if remainder > 0:
        result += ' ' + number_to_hindi_words(remainder)
    return result


def normalize_devanagari(text: str) -> str:
    """Normalize Devanagari text for consistent TTS."""
    # Unicode NFC normalization
    text = unicodedata.normalize('NFC', text)
    
    # Normalize chandrabindu variations
    text = text.replace('ँ', 'ं')  # Some fonts use different chandrabindu
    
    # Normalize nukta variations
    text = re.sub(r'([क-ह])़', r'\1़', text)
    
    # Fix common OCR/transcription errors
    replacements = {
        'ॅ': '',  # Remove rare vowel sign
        'ॆ': 'े',
        'ॊ': 'ो',
        '॰': '.',  # Abbreviation sign to period
        '।': '।',  # Ensure proper danda
        '॥': '॥',  # Ensure proper double danda
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    
    return text


def convert_numbers_in_text(text: str) -> str:
    """Convert all numbers in text to Hindi words."""
    # Convert Devanagari numerals to Arabic
    devanagari_to_arabic = str.maketrans('०१२३४५६७८९', '0123456789')
    text = text.translate(devanagari_to_arabic)
    
    # Find and replace all numbers
    def replace_number(match):
        num_str = match.group()
        try:
            num = int(num_str)
            if num > 0 and num < 100000000:  # Up to 10 crore
                return number_to_hindi_words(num)
            return num_str
        except ValueError:
            return num_str
    
    text = re.sub(r'\d+', replace_number, text)
    return text


def segment_sentences(text: str, max_length: int = 200) -> List[str]:
    """
    Split text into sentences for natural TTS output.
    Respects Hindi punctuation (।) and limits sentence length.
    """
    # Split on Hindi danda and common punctuation
    sentences = re.split(r'[।॥.!?]+', text)
    
    result = []
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        
        # If sentence is too long, split on commas
        if len(sentence) > max_length:
            parts = sentence.split(',')
            current = ""
            for part in parts:
                part = part.strip()
                if len(current) + len(part) + 2 <= max_length:
                    current = current + ", " + part if current else part
                else:
                    if current:
                        result.append(current)
                    current = part
            if current:
                result.append(current)
        else:
            result.append(sentence)
    
    return result


def clean_for_tts(text: str) -> str:
    """Remove markdown and special formatting."""
    # Remove markdown bold/italic
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    text = re.sub(r'`(.*?)`', r'\1', text)
    
    # Remove markdown links
    text = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', text)
    
    # Fix quotation marks
    text = text.replace('"', '"').replace('"', '"')
    text = text.replace(''', "'").replace(''', "'")
    text = text.replace('—', '-').replace('–', '-')
    
    # Normalize whitespace
    text = re.sub(r'\n+', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()


def preprocess_for_tts(text: str) -> str:
    """
    Full preprocessing pipeline for Hindi TTS.
    
    Steps:
    1. Clean markdown and formatting
    2. Normalize Devanagari characters
    3. Convert numbers to Hindi words
    4. Normalize whitespace
    """
    if not text or not text.strip():
        return ""
    
    # Step 1: Clean formatting
    text = clean_for_tts(text)
    
    # Step 2: Normalize Devanagari
    text = normalize_devanagari(text)
    
    # Step 3: Convert numbers
    text = convert_numbers_in_text(text)
    
    # Step 4: Final cleanup
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text


def preprocess_for_tts_chunked(text: str, max_chunk_length: int = 200) -> List[str]:
    """
    Preprocess and split into chunks for TTS.
    Returns list of processed text chunks.
    """
    # First preprocess
    text = preprocess_for_tts(text)
    
    # Then segment
    return segment_sentences(text, max_chunk_length)


# Reference audio metadata
REFERENCE_TRANSCRIPT = """देखों, सबसे पहली बात हमारी कमज़ोरी क्या है? हम परेशान हो जाते हैं। 
संसार में देखो तो परेशान। परमार्थ के मार्ग में देखो तो हम परेशान होते हैं। 
यह हमारा स्वभाव बन गया परेशान होना। थोड़ा सा धीरज बनो, गंभीर बनो।"""


if __name__ == "__main__":
    # Test the processor
    test_texts = [
        "नमस्ते, मैं प्रेमानंद महाराज हूँ।",
        "आज हम भगवद्गीता का अध्याय 15 पढ़ेंगे।",
        "यह 2024 में हुआ था।",
        "१२३ लोग आज यहाँ आए हैं।",
        "**बहुत** अच्छा! यह `कोड` है।",
    ]
    
    print("Hindi Text Processor Tests:")
    print("=" * 50)
    for text in test_texts:
        processed = preprocess_for_tts(text)
        print(f"Input:  {text}")
        print(f"Output: {processed}")
        print("-" * 50)

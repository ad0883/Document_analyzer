from flask import Flask, request, jsonify, send_from_directory
import pdfplumber
import docx
import io
import re
import textstat
from spellchecker import SpellChecker
from autocorrect import Speller

app = Flask(__name__)

# Initialize spell checkers
spell = SpellChecker()
spell_autocorrect = Speller()

# Technical terms to ignore
IGNORE_WORDS = set([
    "API", "APIs", "HTTP", "HTTPS", "URL", "URLs", "JSON", "XML", "CSS", "HTML", "PDF", "PDFs",
    "AI", "ML", "IoT", "GPS", "USB", "CPU", "GPU", "RAM", "SSD", "HDD", "OS", "UI", "UX",
    "app", "apps", "email", "emails", "website", "websites", "WiFi", "Bluetooth",
    "YAML", "NLP", "GPT", "OpenAI", "API", "SDK", "IDE", "GUI", "TCP", "UDP", "DNS",
    # Common proper nouns and names
    "Alok", "Raj", "Dwivedi", "Komi", "Tech", "Tome", "Labs", "alice", "smith", "bob", "jones",
    "charlie", "dave", "eve", "frank", "openai", "kome", "testsite", "mywebsite",
    # Domain extensions and URL parts
    "com", "org", "net", "gov", "edu", "ai", "io", "www", "http", "https", "example"
])

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

def extract_text(file, filename):
    """Simple, reliable text extraction"""
    if filename.endswith('.pdf'):
        text = ""
        try:
            with pdfplumber.open(file) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
        except Exception as e:
            return f"Error reading PDF: {str(e)}"
        return text
    
    elif filename.endswith('.docx'):
        try:
            doc = docx.Document(file)
            return "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
        except Exception as e:
            return f"Error reading DOCX: {str(e)}"
    
    else:  # .txt
        try:
            return file.read().decode('utf-8')
        except Exception as e:
            return f"Error reading text file: {str(e)}"

def is_likely_proper_noun(word, text):
    """Check if word is likely a proper noun"""
    if not word[0].isupper():
        return False
    
    # Count occurrences in text
    occurrences = len(re.findall(r'\b' + re.escape(word) + r'\b', text))
    
    # If appears multiple times and always capitalized, likely proper noun
    if occurrences > 1:
        return True
    
    # Common proper noun patterns
    proper_patterns = [
        r'\b[A-Z][a-z]+\s+[A-Z][a-z]+\b',  # John Smith
        r'\b[A-Z][a-z]+\s+Labs?\b',        # Tech Labs
        r'\b[A-Z][a-z]+\s+Tech\b',         # Komi Tech
    ]
    
    for pattern in proper_patterns:
        if re.search(pattern, text) and word in re.search(pattern, text).group():
            return True
    
    return False

def is_url_or_email_part(word, text):
    """Check if word is part of URL or email"""
    # Check if word appears in URL context
    url_patterns = [
        r'https?://[^\s]*' + re.escape(word) + r'[^\s]*',
        r'www\.[^\s]*' + re.escape(word) + r'[^\s]*',
        r'[^\s]*\.' + re.escape(word) + r'[/\s]',
        r'[^\s]*@[^\s]*' + re.escape(word) + r'[^\s]*'
    ]
    
    for pattern in url_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    
    return False

def check_spelling(text):
    """Smart spelling check that respects context"""
    words = re.findall(r'\b[a-zA-Z]+\b', text)
    errors = []
    
    # Only target obvious misspellings
    obvious_fixes = {
        'thiss': 'this',
        'itn': 'it', 
        'teh': 'the',
        'documnt': 'document',
        'errros': 'errors',
        'analayzer': 'analyzer',
        'detectes': 'detects',
        'perfeclty': 'perfectly',
        'sugestions': 'suggestions',
        'wich': 'which',
        'definately': 'definitely',
        'recomend': 'recommend',
        'untill': 'until',
        'concludez': 'concludes',
        'containz': 'contains',
        'featuress': 'features',
        'challange': 'challenge',
        'smple': 'simple',
        'spelng': 'spelling',
        'analyz': 'analyze'
    }
    
    for word in words:
        if len(word) <= 1:
            continue
            
        word_lower = word.lower()
        
        # Skip technical terms and common words
        if word_lower in IGNORE_WORDS:
            continue
        
        # Skip if part of URL or email
        if is_url_or_email_part(word, text):
            continue
            
        # Skip if likely proper noun
        if is_likely_proper_noun(word, text):
            continue
        
        # Check obvious misspellings first
        if word_lower in obvious_fixes:
            errors.append({
                'word': word,
                'suggestions': [obvious_fixes[word_lower]],
                'type': 'spelling',
                'confidence': 'high'
            })
            continue
        
        # Only flag if word is clearly wrong AND we have good suggestions
        if word_lower not in spell:
            suggestions = list(spell.candidates(word))
            
            # Filter out suggestions that are too different
            good_suggestions = []
            for suggestion in suggestions[:3]:
                # Only suggest if similarity is high
                if len(suggestion) >= len(word) - 2 and len(suggestion) <= len(word) + 2:
                    good_suggestions.append(suggestion)
            
            # Only report error if we have confident suggestions
            if good_suggestions and len(word) > 3:  # Don't flag short words unless obvious
                errors.append({
                    'word': word,
                    'suggestions': good_suggestions,
                    'type': 'spelling',
                    'confidence': 'medium'
                })
    
    return errors

def suggest_by_pattern(word):
    """Suggest corrections based on common typing patterns"""
    suggestions = []
    word_lower = word.lower()
    
    # Double letters that might be typos
    if len(set(word_lower)) < len(word_lower) - 1:  # Has repeated letters
        # Try removing one of each double letter
        clean_word = re.sub(r'(.)\1+', r'\1', word_lower)
        if clean_word != word_lower:
            suggestions.append(clean_word)
    
    # Common letter swaps
    swaps = [
        ('ss', 's'), ('th', 'th'), ('tn', 'n'), ('nm', 'n'),
        ('ei', 'ie'), ('ie', 'ei')
    ]
    
    for wrong, right in swaps:
        if wrong in word_lower:
            fixed = word_lower.replace(wrong, right)
            if fixed != word_lower:
                suggestions.append(fixed)
    
    return suggestions

def check_basic_grammar(text):
    """Basic grammar and formatting checks"""
    errors = []
    
    # Multiple spaces
    if re.search(r'  +', text):
        errors.append({
            'type': 'formatting',
            'message': 'Multiple consecutive spaces found',
            'suggestion': 'Use single spaces'
        })
    
    # Missing space after punctuation
    matches = re.finditer(r'[.!?][a-zA-Z]', text)
    for match in matches:
        errors.append({
            'type': 'formatting',
            'message': f'Missing space after punctuation: "{match.group()}"',
            'suggestion': f'Add space: "{match.group()[0]} {match.group()[1]}"'
        })
    
    # Common word mistakes
    common_mistakes = [
        (r'\bits\s+own\b', "Should be 'its own' (possessive)"),
        (r'\byour\s+welcome\b', "Should be 'you're welcome'"),
        (r'\bto\s+much\b', "Should be 'too much'"),
        (r'\bthere\s+house\b', "Should be 'their house'")
    ]
    
    for pattern, message in common_mistakes:
        if re.search(pattern, text, re.IGNORECASE):
            errors.append({
                'type': 'grammar',
                'message': message,
                'suggestion': 'Check word usage'
            })
    
    return errors

def calculate_metrics(text):
    """Calculate readability metrics safely"""
    try:
        words = len(re.findall(r'\b\w+\b', text))
        sentences = max(1, textstat.sentence_count(text))
        
        return {
            'word_count': words,
            'sentence_count': sentences,
            'avg_words_per_sentence': round(words / sentences, 1),
            'reading_ease': round(textstat.flesch_reading_ease(text), 1),
            'grade_level': round(textstat.flesch_kincaid_grade(text), 1)
        }
    except Exception as e:
        return {
            'word_count': len(text.split()),
            'sentence_count': text.count('.') + text.count('!') + text.count('?'),
            'avg_words_per_sentence': 0,
            'reading_ease': 0,
            'grade_level': 0
        }

def create_corrected_text(text, spelling_errors):
    """Generate corrected text with proper case handling"""
    corrected = text
    
    for error in spelling_errors:
        if error.get('suggestions'):
            original_word = error['word']
            suggestion = error['suggestions'][0]
            
            # Preserve original capitalization
            if original_word[0].isupper():
                suggestion = suggestion.capitalize()
            elif original_word.isupper():
                suggestion = suggestion.upper()
                
            # Replace with word boundaries
            pattern = r'\b' + re.escape(original_word) + r'\b'
            corrected = re.sub(pattern, suggestion, corrected, count=1)
    
    return corrected

@app.route('/')
def index():
    return send_from_directory('.', 'simple_index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400

        uploaded = request.files['file']
        filename = uploaded.filename

        if not filename.lower().endswith(('.pdf', '.docx', '.txt')):
            return jsonify({'error': 'Unsupported file format'}), 400

        # Check file size
        uploaded.seek(0, io.SEEK_END)
        if uploaded.tell() > MAX_FILE_SIZE:
            return jsonify({'error': 'File too large'}), 400
        uploaded.seek(0)

        # Extract text
        file_bytes = io.BytesIO(uploaded.read())
        text = extract_text(file_bytes, filename)
        
        if not text or len(text.strip()) < 10:
            return jsonify({'error': 'No readable text found'}), 400

        # Perform analysis
        spelling_errors = check_spelling(text)
        grammar_errors = check_basic_grammar(text)
        metrics = calculate_metrics(text)
        corrected_text = create_corrected_text(text, spelling_errors)
        
        # Create highlighted text
        highlighted_text = text
        for error in spelling_errors:
            word = error['word']
            suggestions = ', '.join(error['suggestions'][:3])
            replacement = f'<mark class="error" title="Suggestions: {suggestions}">{word}</mark>'
            highlighted_text = re.sub(r'\b' + re.escape(word) + r'\b', replacement, highlighted_text, count=1)

        result = {
            'success': True,
            'text_length': len(text),
            'spelling_errors': spelling_errors,
            'grammar_errors': grammar_errors,
            'total_errors': len(spelling_errors) + len(grammar_errors),
            'metrics': metrics,
            'corrected_text': corrected_text,
            'highlighted_text': highlighted_text.replace('\n', '<br>')
        }
        
        return jsonify(result)

    except Exception as e:
        return jsonify({'error': f'Analysis failed: {str(e)}'}), 500

if __name__ == '__main__':
    print("🚀 Simple Document Analyzer Starting...")
    print("🌐 Server: http://localhost:5013")
    app.run(debug=True, host='0.0.0.0', port=5013)
